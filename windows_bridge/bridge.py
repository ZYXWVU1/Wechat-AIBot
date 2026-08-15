r"""Self-contained Windows VM bridge for WeChatFerry 39.5.2.0.

Run from the existing WCF virtual environment with::

    .\.venv\Scripts\python.exe bridge.py

Required environment variable: WCF_BRIDGE_KEY.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from queue import Empty
from typing import Any, Iterator, Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


LOG = logging.getLogger("wcf-bridge")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def csv_set(value: str) -> frozenset[str]:
    return frozenset(item.strip() for item in value.split(",") if item.strip())


BRIDGE_KEY = os.getenv("WCF_BRIDGE_KEY", "").strip()
BRIDGE_HOST = os.getenv("WCF_BRIDGE_HOST", "127.0.0.1").strip()
BRIDGE_PORT = int(os.getenv("WCF_BRIDGE_PORT", "8787"))
ALLOWED_RECEIVERS = csv_set(os.getenv("WCF_ALLOWED_RECEIVERS", "filehelper"))
EVENT_RETENTION_DAYS = int(os.getenv("WCF_EVENT_RETENTION_DAYS", "7"))
MIN_SEND_INTERVAL = float(os.getenv("WCF_MIN_SEND_INTERVAL_SECONDS", "2.0"))
DATA_DIR = Path(
    os.getenv("WCF_DATA_DIR", str(Path(__file__).resolve().parent / "data"))
).expanduser()

if len(BRIDGE_KEY) < 32:
    raise RuntimeError("WCF_BRIDGE_KEY must contain at least 32 characters")
if not ALLOWED_RECEIVERS:
    raise RuntimeError("WCF_ALLOWED_RECEIVERS cannot be empty")
if not 1 <= BRIDGE_PORT <= 65535:
    raise RuntimeError("WCF_BRIDGE_PORT must be between 1 and 65535")
if EVENT_RETENTION_DAYS <= 0 or MIN_SEND_INTERVAL < 0:
    raise RuntimeError("Retention must be positive and send interval non-negative")


class BridgeStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
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
        with self.connection() as connection:
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
            return int(cursor.lastrowid) if cursor.rowcount else None

    def list_events(self, after: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        with self.connection() as connection:
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
            latest = int(
                connection.execute(
                    "SELECT COALESCE(MAX(event_id), 0) FROM events"
                ).fetchone()[0]
            )

        events = []
        for row in rows:
            event = dict(row)
            event["is_text"] = bool(event["is_text"])
            event["is_group"] = bool(event["is_group"])
            event["at_me"] = bool(event["at_me"])
            events.append(event)
        return events, latest

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_send(self, request_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT request_id, receiver, content_hash, result
                FROM send_requests WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_send(
        self, request_id: str, receiver: str, content: str, result: int
    ) -> None:
        with self.connection() as connection:
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

    def prune(self) -> None:
        cutoff = int(time.time()) - EVENT_RETENTION_DAYS * 86400
        with self.connection() as connection:
            connection.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
            connection.execute(
                "DELETE FROM send_requests WHERE created_at < ?", (cutoff,)
            )


STORE = BridgeStore(DATA_DIR / "bridge.db")
wcf = None
self_wxid = ""
stop_event = threading.Event()
send_lock = threading.Lock()
last_send_by_receiver: dict[str, float] = {}


class SendRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    receiver: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=500)
    at_users: str = Field(default="", max_length=1000)


def require_key(x_bridge_key: Optional[str] = Header(default=None)) -> None:
    if not secrets.compare_digest(x_bridge_key or "", BRIDGE_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")


def receive_messages() -> None:
    while not stop_event.is_set():
        try:
            message = wcf.get_msg()
        except Empty:
            continue
        except Exception:
            LOG.exception("WCF receive failed")
            stop_event.wait(1)
            continue

        if message.from_self():
            continue

        STORE.append_event(
            {
                "wechat_message_id": str(message.id),
                "timestamp": int(message.ts),
                "type": int(message.type),
                "is_text": bool(message.is_text()),
                "is_group": bool(message.from_group()),
                "at_me": bool(message.is_at(self_wxid)),
                "sender": message.sender or "",
                "roomid": message.roomid or "",
                "receiver": message.roomid
                if message.from_group()
                else message.sender,
                "content": message.content or "",
            }
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global wcf, self_wxid

    from wcferry import Wcf

    STORE.prune()
    stop_event.clear()
    wcf = Wcf(debug=False, block=True)
    self_wxid = wcf.get_self_wxid()
    if not wcf.enable_receiving_msg():
        wcf.cleanup()
        raise RuntimeError("Unable to enable WCF message receiving")

    thread = threading.Thread(
        target=receive_messages,
        name="WCFMessageReceiver",
        daemon=True,
    )
    thread.start()
    LOG.info("Bridge started; %d receiver(s) allowed", len(ALLOWED_RECEIVERS))
    try:
        yield
    finally:
        stop_event.set()
        if wcf is not None:
            wcf.cleanup()
        LOG.info("Bridge stopped")


app = FastAPI(
    title="WCF Secure Bridge",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health", dependencies=[Depends(require_key)])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "wechat_login": bool(wcf and wcf.is_login()),
        "receiving": bool(wcf and wcf.is_receiving_msg()),
        "allowed_receiver_count": len(ALLOWED_RECEIVERS),
    }


@app.get("/events", dependencies=[Depends(require_key)])
def get_events(
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, object]:
    events, latest = STORE.list_events(after, limit)
    return {"events": events, "latest_event_id": latest}


@app.post("/send", dependencies=[Depends(require_key)])
def send_message(payload: SendRequest) -> dict[str, object]:
    if payload.receiver not in ALLOWED_RECEIVERS:
        raise HTTPException(status_code=403, detail="Receiver is not allowed")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    expected_hash = STORE.content_hash(content)

    with send_lock:
        existing = STORE.get_send(payload.request_id)
        if existing:
            if (
                existing["receiver"] != payload.receiver
                or existing["content_hash"] != expected_hash
            ):
                raise HTTPException(status_code=409, detail="request_id payload mismatch")
            if existing["result"] != 0:
                raise HTTPException(
                    status_code=502,
                    detail=f"WCF send failed with status {existing['result']}",
                )
            return {
                "ok": True,
                "result": 0,
                "receiver": payload.receiver,
                "duplicate": True,
            }

        now = time.monotonic()
        previous = last_send_by_receiver.get(payload.receiver, 0.0)
        remaining = MIN_SEND_INTERVAL - (now - previous)
        if remaining > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limited; retry after {remaining:.2f} seconds",
                headers={"Retry-After": str(max(1, int(remaining) + 1))},
            )

        result = int(
            wcf.send_text(content, payload.receiver, payload.at_users or "")
        )
        last_send_by_receiver[payload.receiver] = time.monotonic()
        STORE.record_send(payload.request_id, payload.receiver, content, result)

    if result != 0:
        raise HTTPException(
            status_code=502,
            detail=f"WCF send failed with status {result}",
        )
    return {
        "ok": True,
        "result": result,
        "receiver": payload.receiver,
        "duplicate": False,
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=BRIDGE_HOST,
        port=BRIDGE_PORT,
        workers=1,
        log_level="info",
    )
