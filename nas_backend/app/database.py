from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bridge_event_id INTEGER,
                    wechat_message_id TEXT,
                    conversation_id TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(bridge_event_id),
                    UNIQUE(wechat_message_id, direction)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, id DESC);

                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    content TEXT NOT NULL,
                    at_users TEXT NOT NULL,
                    due_at REAL NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','sending','sent','failed','cancelled','suppressed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    sent_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_outbox_due
                    ON outbox(status, due_at);
                """
            )
            connection.execute(
                "UPDATE outbox SET status = 'pending' WHERE status = 'sending'"
            )

    def get_cursor(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = 'bridge_cursor'"
            ).fetchone()
        return int(row["value"]) if row else 0

    def set_cursor(self, value: int) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES('bridge_cursor', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(value),),
            )

    def add_inbound(self, event: dict[str, Any], conversation_id: str) -> bool:
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO messages (
                        bridge_event_id, wechat_message_id, conversation_id,
                        direction, sender, receiver, content, timestamp, created_at
                    ) VALUES (?, ?, ?, 'inbound', ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_id"],
                        event["wechat_message_id"],
                        conversation_id,
                        event["sender"],
                        event["receiver"],
                        event["content"],
                        event["timestamp"],
                        time.time(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def add_outbound_message(
        self, conversation_id: str, receiver: str, content: str
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    bridge_event_id, wechat_message_id, conversation_id,
                    direction, sender, receiver, content, timestamp, created_at
                ) VALUES (NULL, NULL, ?, 'outbound', 'self', ?, ?, ?, ?)
                """,
                (conversation_id, receiver, content, int(time.time()), time.time()),
            )

    def history(self, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT direction, sender, receiver, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def cancel_pending(self, conversation_id: str) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET status = 'cancelled'
                WHERE conversation_id = ? AND status = 'pending'
                """,
                (conversation_id,),
            )
        return cursor.rowcount

    def enqueue(
        self,
        conversation_id: str,
        receiver: str,
        content: str,
        at_users: str,
        due_at: float,
    ) -> str:
        item_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO outbox (
                    id, conversation_id, receiver, content, at_users,
                    due_at, status, attempts, last_error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, '', ?)
                """,
                (
                    item_id,
                    conversation_id,
                    receiver,
                    content,
                    at_users,
                    due_at,
                    time.time(),
                ),
            )
        return item_id

    def claim_due(self) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM outbox
                WHERE status = 'pending' AND due_at <= ?
                ORDER BY due_at ASC
                LIMIT 1
                """,
                (time.time(),),
            ).fetchone()
            if not row:
                connection.commit()
                return None
            connection.execute(
                "UPDATE outbox SET status = 'sending' WHERE id = ?",
                (row["id"],),
            )
            connection.commit()
            return dict(row)
        finally:
            connection.close()

    def mark_sent(self, item_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE outbox SET status = 'sent', sent_at = ? WHERE id = ?",
                (time.time(), item_id),
            )

    def mark_suppressed(self, item_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE outbox SET status = 'suppressed' WHERE id = ?",
                (item_id,),
            )

    def retry_or_fail(
        self, item_id: str, attempts: int, error: str, max_attempts: int
    ) -> None:
        next_attempt = attempts + 1
        status = "failed" if next_attempt >= max_attempts else "pending"
        retry_at = time.time() + min(300, 2**next_attempt)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE outbox
                SET status = ?, attempts = ?, last_error = ?, due_at = ?
                WHERE id = ?
                """,
                (status, next_attempt, error[:1000], retry_at, item_id),
            )
