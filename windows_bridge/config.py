from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv_set(value: str) -> frozenset[str]:
    return frozenset(item.strip() for item in value.split(",") if item.strip())


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _non_negative_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


@dataclass(frozen=True)
class BridgeConfig:
    bridge_key: str
    host: str
    port: int
    allowed_receivers: frozenset[str]
    data_dir: Path
    event_retention_days: int
    min_send_interval_seconds: float

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        bridge_key = os.getenv("WCF_BRIDGE_KEY", "").strip()
        if len(bridge_key) < 32:
            raise RuntimeError("WCF_BRIDGE_KEY must contain at least 32 characters")

        allowed = _csv_set(os.getenv("WCF_ALLOWED_RECEIVERS", "filehelper"))
        if not allowed:
            raise RuntimeError("WCF_ALLOWED_RECEIVERS cannot be empty")

        default_data_dir = Path(__file__).resolve().parent / "data"
        data_dir = Path(os.getenv("WCF_DATA_DIR", str(default_data_dir))).expanduser()

        return cls(
            bridge_key=bridge_key,
            host=os.getenv("WCF_BRIDGE_HOST", "127.0.0.1").strip(),
            port=_positive_int("WCF_BRIDGE_PORT", 8787),
            allowed_receivers=allowed,
            data_dir=data_dir,
            event_retention_days=_positive_int("WCF_EVENT_RETENTION_DAYS", 7),
            min_send_interval_seconds=_non_negative_float(
                "WCF_MIN_SEND_INTERVAL_SECONDS", 2.0
            ),
        )

