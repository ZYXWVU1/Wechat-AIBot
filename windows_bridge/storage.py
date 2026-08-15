from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class BridgeStore:
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
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wechat_message_id TEXT NOT NULL UNIQUE,
                    timestamp INTEGER NOT NULL,
                    message_type INTEGER NOT NULL,
                    is_text INTEGER NOT NULL,
                    is_group INTEGER NOT NULL,
                    at_me INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    roomid TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_created_at
                    ON events(created_at);

                CREATE TABLE IF NOT EXISTS send_requests (
                    request_id TEXT PRIMARY KEY,
                    receiver TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    result INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )

    def append_event(self, event: dict[str, Any]) -> int | None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO events (
                    wechat_message_id, timestamp, message_type, is_text,
                    is_group, at_me, sender, roomid, receiver, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["wechat_message_id"],
                    event["timestamp"],
                    event["type"],
                    int(event["is_text"]),
                    int(event["is_group"]),
                    int(event["at_me"]),
                    event["sender"],
                    event["roomid"],
                    event["receiver"],
                    event["content"],
                    int(time.time()),
                ),
            )
            if cursor.rowcount == 0:
                return None
            return int(cursor.lastrowid)

    def list_events(self, after: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, wechat_message_id, timestamp,
                       message_type AS type, is_text, is_group, at_me,
                       sender, roomid, receiver, content
                FROM events
                WHERE event_id > ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (after, limit),
            ).fetchall()
            latest_row = connection.execute(
                "SELECT COALESCE(MAX(event_id), 0) AS latest FROM events"
            ).fetchone()

        events = []
        for row in rows:
            item = dict(row)
            item["is_text"] = bool(item["is_text"])
            item["is_group"] = bool(item["is_group"])
            item["at_me"] = bool(item["at_me"])
            events.append(item)
        return events, int(latest_row["latest"])

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_send_result(self, request_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT request_id, receiver, content_hash, result, created_at
                FROM send_requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_send_result(
        self, request_id: str, receiver: str, content: str, result: int
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO send_requests (
                    request_id, receiver, content_hash, result, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    receiver,
                    self.content_hash(content),
                    result,
                    int(time.time()),
                ),
            )

    def prune(self, retention_days: int) -> int:
        cutoff = int(time.time()) - retention_days * 86400
        with self._connection() as connection:
            event_cursor = connection.execute(
                "DELETE FROM events WHERE created_at < ?", (cutoff,)
            )
            connection.execute(
                "DELETE FROM send_requests WHERE created_at < ?", (cutoff,)
            )
        return event_cursor.rowcount

    def diagnostics(self) -> str:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS event_count FROM events"
            ).fetchone()
        return json.dumps({"event_count": int(row["event_count"])})
