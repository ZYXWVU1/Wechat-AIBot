from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings


@dataclass(frozen=True)
class Decision:
    should_reply: bool
    reason: str
    conversation_id: str
    receiver: str
    at_users: str = ""


def decide(event: dict[str, Any], settings: Settings) -> Decision:
    is_group = bool(event.get("is_group"))
    conversation_id = event.get("roomid") if is_group else event.get("sender")
    receiver = event.get("receiver") or conversation_id or ""
    base = {
        "conversation_id": conversation_id or "",
        "receiver": receiver,
    }

    if not settings.auto_reply_enabled:
        return Decision(False, "auto_reply_disabled", **base)
    if not event.get("is_text") or int(event.get("type", 0)) != 1:
        return Decision(False, "not_text", **base)
    if not str(event.get("content", "")).strip():
        return Decision(False, "empty_text", **base)

    if is_group:
        roomid = str(event.get("roomid", ""))
        if not settings.group_reply_enabled:
            return Decision(False, "group_reply_disabled", **base)
        if roomid not in settings.allowed_groups:
            return Decision(False, "group_not_allowed", **base)
        if not event.get("at_me"):
            return Decision(False, "not_mentioned", **base)
        return Decision(True, "allowed_group_mention", **base)

    sender = str(event.get("sender", ""))
    if not settings.direct_reply_enabled:
        return Decision(False, "direct_reply_disabled", **base)
    if sender not in settings.allowed_direct_senders:
        return Decision(False, "sender_not_allowed", **base)
    return Decision(True, "allowed_direct_message", **base)

