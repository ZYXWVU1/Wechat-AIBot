from __future__ import annotations

import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager
from queue import Empty
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from config import BridgeConfig
from storage import BridgeStore


LOG = logging.getLogger("wcf-bridge")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

CONFIG = BridgeConfig.from_env()
STORE = BridgeStore(CONFIG.data_dir / "bridge.db")

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
    supplied = x_bridge_key or ""
    if not secrets.compare_digest(supplied, CONFIG.bridge_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


def receive_messages() -> None:
    while not stop_event.is_set():
        try:
            message = wcf.get_msg()
        except Empty:
            continue
        except Exception:
            LOG.exception("WCF receive failed")
            time.sleep(1)
            continue

        if message.from_self():
            continue

        event = {
            "wechat_message_id": str(message.id),
            "timestamp": int(message.ts),
            "type": int(message.type),
            "is_text": bool(message.is_text()),
            "is_group": bool(message.from_group()),
            "at_me": bool(message.is_at(self_wxid)),
            "sender": message.sender or "",
            "roomid": message.roomid or "",
            "receiver": message.roomid if message.from_group() else message.sender,
            "content": message.content or "",
        }
        STORE.append_event(event)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global wcf, self_wxid

    from wcferry import Wcf

    STORE.prune(CONFIG.event_retention_days)
    stop_event.clear()
    wcf = Wcf(debug=False, block=True)
    self_wxid = wcf.get_self_wxid()

    if not wcf.enable_receiving_msg():
        wcf.cleanup()
        raise RuntimeError("Unable to enable WCF message receiving")

    receiver_thread = threading.Thread(
        target=receive_messages,
        name="WCFMessageReceiver",
        daemon=True,
    )
    receiver_thread.start()
    LOG.info("Bridge started; %d receiver(s) allowed", len(CONFIG.allowed_receivers))

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
        "allowed_receiver_count": len(CONFIG.allowed_receivers),
    }


@app.get("/events", dependencies=[Depends(require_key)])
def get_events(
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, object]:
    events, latest = STORE.list_events(after=after, limit=limit)
    return {"events": events, "latest_event_id": latest}


@app.post("/send", dependencies=[Depends(require_key)])
def send_message(payload: SendRequest) -> dict[str, object]:
    if payload.receiver not in CONFIG.allowed_receivers:
        raise HTTPException(status_code=403, detail="Receiver is not allowed")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    expected_hash = STORE.content_hash(content)
    with send_lock:
        existing = STORE.get_send_result(payload.request_id)
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
                "result": existing["result"],
                "receiver": payload.receiver,
                "duplicate": True,
            }

        now = time.monotonic()
        previous = last_send_by_receiver.get(payload.receiver, 0.0)
        remaining = CONFIG.min_send_interval_seconds - (now - previous)
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
        STORE.record_send_result(
            payload.request_id, payload.receiver, content, result
        )

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
