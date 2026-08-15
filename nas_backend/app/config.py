from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _optional_bool(name: str) -> bool | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return _bool(name)


def _csv_set(name: str) -> frozenset[str]:
    return frozenset(
        item.strip() for item in os.getenv(name, "").split(",") if item.strip()
    )


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    value = float(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _int(name: str, default: int, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    bridge_url: str
    bridge_key: str
    auto_reply_enabled: bool
    dry_run: bool
    direct_reply_enabled: bool
    group_reply_enabled: bool
    allowed_direct_senders: frozenset[str]
    allowed_groups: frozenset[str]
    ai_provider: str
    ai_chat_completions_url: str
    ai_api_key: str
    ai_model: str
    ai_enable_thinking: bool | None
    ai_temperature: float
    ai_max_tokens: int
    persona: str
    disclosure_prefix: str
    max_context_messages: int
    max_reply_chars: int
    max_chunk_chars: int
    max_chunks: int
    read_delay_min_seconds: float
    read_delay_max_seconds: float
    typing_seconds_per_character: float
    chunk_gap_min_seconds: float
    chunk_gap_max_seconds: float
    reply_probability: float
    database_path: Path
    poll_interval_seconds: float
    outbox_poll_seconds: float
    max_send_attempts: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        bridge_url = os.getenv("BRIDGE_URL", "").strip().rstrip("/")
        bridge_key = os.getenv("BRIDGE_KEY", "").strip()
        if not bridge_url.startswith(("http://", "https://")):
            raise RuntimeError("BRIDGE_URL must start with http:// or https://")
        if len(bridge_key) < 32:
            raise RuntimeError("BRIDGE_KEY must contain at least 32 characters")

        persona_path = Path(os.getenv("PERSONA_FILE", "/config/persona.txt"))
        if not persona_path.is_file():
            raise RuntimeError(f"Persona file not found: {persona_path}")
        persona = persona_path.read_text(encoding="utf-8").strip()
        if not persona:
            raise RuntimeError("Persona file cannot be empty")

        ai_provider = os.getenv("AI_PROVIDER", "disabled").strip().lower()
        if ai_provider not in {"disabled", "http_chat_completions"}:
            raise RuntimeError(
                "AI_PROVIDER must be disabled or http_chat_completions"
            )
        ai_url = os.getenv("AI_CHAT_COMPLETIONS_URL", "").strip()
        ai_model = os.getenv("AI_MODEL", "").strip()
        if ai_provider != "disabled" and (not ai_url or not ai_model):
            raise RuntimeError(
                "AI_CHAT_COMPLETIONS_URL and AI_MODEL are required when AI is enabled"
            )

        delay_min = _float("READ_DELAY_MIN_SECONDS", 3)
        delay_max = _float("READ_DELAY_MAX_SECONDS", 7)
        gap_min = _float("CHUNK_GAP_MIN_SECONDS", 1)
        gap_max = _float("CHUNK_GAP_MAX_SECONDS", 3)
        if delay_max < delay_min:
            raise ValueError("READ_DELAY_MAX_SECONDS must be >= minimum")
        if gap_max < gap_min:
            raise ValueError("CHUNK_GAP_MAX_SECONDS must be >= minimum")

        probability = _float("REPLY_PROBABILITY", 1.0)
        if probability > 1:
            raise ValueError("REPLY_PROBABILITY cannot exceed 1.0")

        return cls(
            bridge_url=bridge_url,
            bridge_key=bridge_key,
            auto_reply_enabled=_bool("AUTO_REPLY_ENABLED"),
            dry_run=_bool("DRY_RUN", True),
            direct_reply_enabled=_bool("DIRECT_REPLY_ENABLED"),
            group_reply_enabled=_bool("GROUP_REPLY_ENABLED"),
            allowed_direct_senders=_csv_set("ALLOWED_DIRECT_SENDERS"),
            allowed_groups=_csv_set("ALLOWED_GROUPS"),
            ai_provider=ai_provider,
            ai_chat_completions_url=ai_url,
            ai_api_key=os.getenv("AI_API_KEY", "").strip(),
            ai_model=ai_model,
            ai_enable_thinking=_optional_bool("AI_ENABLE_THINKING"),
            ai_temperature=_float("AI_TEMPERATURE", 0.8),
            ai_max_tokens=_int("AI_MAX_TOKENS", 300),
            persona=persona,
            disclosure_prefix=os.getenv("DISCLOSURE_PREFIX", "🤖 "),
            max_context_messages=_int("MAX_CONTEXT_MESSAGES", 20),
            max_reply_chars=_int("MAX_REPLY_CHARS", 360),
            max_chunk_chars=_int("MAX_CHUNK_CHARS", 120),
            max_chunks=_int("MAX_CHUNKS", 3),
            read_delay_min_seconds=delay_min,
            read_delay_max_seconds=delay_max,
            typing_seconds_per_character=_float(
                "TYPING_SECONDS_PER_CHARACTER", 0.12
            ),
            chunk_gap_min_seconds=gap_min,
            chunk_gap_max_seconds=gap_max,
            reply_probability=probability,
            database_path=Path(os.getenv("DATABASE_PATH", "/data/bot.db")),
            poll_interval_seconds=_float("POLL_INTERVAL_SECONDS", 1, 0.1),
            outbox_poll_seconds=_float("OUTBOX_POLL_SECONDS", 0.5, 0.1),
            max_send_attempts=_int("MAX_SEND_ATTEMPTS", 5),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )
