from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

from .ai import AIError, AIProvider
from .bridge_client import BridgeClient, BridgeError
from .chunking import chunk_text
from .config import Settings
from .database import Database
from .policy import decide


LOG = logging.getLogger("bot-service")


class BotService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        bridge: BridgeClient,
        ai: AIProvider,
    ):
        self.settings = settings
        self.database = database
        self.bridge = bridge
        self.ai = ai
        self.stop_event = threading.Event()
        self.random = random.SystemRandom()

    def run_forever(self) -> None:
        health = self.bridge.health()
        if not health.get("wechat_login") or not health.get("receiving"):
            raise RuntimeError(f"Bridge is not ready: {health}")

        LOG.info(
            "Backend started; auto_reply=%s dry_run=%s AI=%s",
            self.settings.auto_reply_enabled,
            self.settings.dry_run,
            self.settings.ai_provider,
        )
        sender = threading.Thread(
            target=self._outbox_loop,
            name="OutboxWorker",
            daemon=True,
        )
        sender.start()

        while not self.stop_event.is_set():
            try:
                self._poll_once()
            except BridgeError as error:
                LOG.warning("Bridge poll failed: %s", error)
                self.stop_event.wait(min(30, self.settings.poll_interval_seconds * 5))
            except Exception:
                LOG.exception("Unexpected poll failure")
                self.stop_event.wait(5)

    def stop(self) -> None:
        self.stop_event.set()

    def _poll_once(self) -> None:
        cursor = self.database.get_cursor()
        response = self.bridge.events(after=cursor, limit=100)
        latest = int(response.get("latest_event_id", 0))
        if latest < cursor:
            LOG.warning("Bridge event sequence reset; replaying with database deduplication")
            cursor = 0
            self.database.set_cursor(0)
            response = self.bridge.events(after=0, limit=100)

        events = response.get("events", [])
        if not events:
            self.stop_event.wait(self.settings.poll_interval_seconds)
            return

        for event in events:
            self._process_event(event)
            self.database.set_cursor(int(event["event_id"]))

    def _process_event(self, event: dict[str, Any]) -> None:
        decision = decide(event, self.settings)
        conversation_id = decision.conversation_id or event.get("sender", "unknown")
        inserted = self.database.add_inbound(event, conversation_id)
        if not inserted:
            return

        cancelled = self.database.cancel_pending(conversation_id)
        if cancelled:
            LOG.info("Cancelled %d pending fragment(s) after a new inbound message", cancelled)

        if not decision.should_reply:
            LOG.info("Message retained without reply: %s", decision.reason)
            return
        if self.random.random() > self.settings.reply_probability:
            LOG.info("Selective reply skipped an eligible message")
            return

        history = self.database.history(
            conversation_id, self.settings.max_context_messages
        )
        try:
            reply = self.ai.generate(history)
        except AIError as error:
            LOG.error("AI generation failed: %s", error)
            return
        if not reply:
            LOG.info("AI provider disabled or returned no reply")
            return

        reply = reply.strip()
        if self.settings.disclosure_prefix:
            reply = f"{self.settings.disclosure_prefix}{reply}"
        reply = reply[: self.settings.max_reply_chars].strip()
        chunks = chunk_text(
            reply,
            max_chars=self.settings.max_chunk_chars,
            max_chunks=self.settings.max_chunks,
        )
        if not chunks:
            return

        due_at = time.time() + self.random.uniform(
            self.settings.read_delay_min_seconds,
            self.settings.read_delay_max_seconds,
        )
        for chunk in chunks:
            due_at += len(chunk) * self.settings.typing_seconds_per_character
            self.database.enqueue(
                conversation_id=conversation_id,
                receiver=decision.receiver,
                content=chunk,
                at_users=decision.at_users,
                due_at=due_at,
            )
            due_at += self.random.uniform(
                self.settings.chunk_gap_min_seconds,
                self.settings.chunk_gap_max_seconds,
            )
        LOG.info("Scheduled %d reply fragment(s)", len(chunks))

    def _outbox_loop(self) -> None:
        while not self.stop_event.is_set():
            item = self.database.claim_due()
            if not item:
                self.stop_event.wait(self.settings.outbox_poll_seconds)
                continue

            try:
                if self.settings.dry_run:
                    LOG.info("DRY_RUN: suppressed one outbound message")
                    self.database.mark_suppressed(item["id"])
                else:
                    self.bridge.send_text(
                        request_id=item["id"],
                        receiver=item["receiver"],
                        content=item["content"],
                        at_users=item["at_users"],
                    )
                    self.database.mark_sent(item["id"])
                    self.database.add_outbound_message(
                        item["conversation_id"], item["receiver"], item["content"]
                    )
            except BridgeError as error:
                LOG.warning("Outbox send failed: %s", error)
                self.database.retry_or_fail(
                    item_id=item["id"],
                    attempts=int(item["attempts"]),
                    error=str(error),
                    max_attempts=self.settings.max_send_attempts,
                )
            except Exception as error:
                LOG.exception("Unexpected outbox failure")
                self.database.retry_or_fail(
                    item_id=item["id"],
                    attempts=int(item["attempts"]),
                    error=str(error),
                    max_attempts=self.settings.max_send_attempts,
                )
