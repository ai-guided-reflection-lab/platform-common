from __future__ import annotations

from contextvars import ContextVar, Token
import hashlib
import json
import logging
import re
import sys
from typing import Any

from app import settings


LOGGER = logging.getLogger("app.pipeline")
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

_trace_id: ContextVar[str | None] = ContextVar("pipeline_trace_id", default=None)
_conversation_id: ContextVar[str | None] = ContextVar("pipeline_conversation_id", default=None)

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


def begin_trace(trace_id: str, conversation_id: str | None = None) -> tuple[Token, Token]:
    return _trace_id.set(trace_id), _conversation_id.set(conversation_id)


def end_trace(tokens: tuple[Token, Token]) -> None:
    trace_token, conversation_token = tokens
    _conversation_id.reset(conversation_token)
    _trace_id.reset(trace_token)


def set_conversation_id(conversation_id: str | None) -> None:
    _conversation_id.set(conversation_id)


def trace_active() -> bool:
    return _trace_id.get() is not None


def _field(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if any(character.isspace() for character in text) or "=" in text:
        return json.dumps(text, ensure_ascii=True)
    return text


def log_event(stage: int | str, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    trace_id = _trace_id.get()
    if not trace_id:
        return
    values = {
        "trace_id": trace_id,
        "conversation_id": _conversation_id.get(),
        "stage": stage,
        "event": event,
        **fields,
    }
    LOGGER.log(level, " ".join(f"{key}={_field(value)}" for key, value in values.items()))


def log_exception(stage: int | str, event: str, error: BaseException, **fields: Any) -> None:
    trace_id = _trace_id.get()
    if not trace_id:
        return
    values = {
        "trace_id": trace_id,
        "conversation_id": _conversation_id.get(),
        "stage": stage,
        "event": event,
        "error_type": type(error).__name__,
        **fields,
    }
    LOGGER.error(" ".join(f"{key}={_field(value)}" for key, value in values.items()))


def debug_digest(label: str, value: str) -> None:
    """Log a non-reversible content fingerprint only when explicitly enabled."""
    if not settings.DEBUG_PIPELINE_LOGS:
        return
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    log_event("debug", f"{label}_digest", chars=len(value), sha256=digest)


def redacted_preview(value: str, max_chars: int = 240) -> str:
    cleaned = " ".join(value.split())
    cleaned = _EMAIL_PATTERN.sub("[redacted-email]", cleaned)
    cleaned = _SECRET_PATTERN.sub("[redacted-secret]", cleaned)
    if len(cleaned) > max_chars:
        return f"{cleaned[:max_chars].rstrip()}…"
    return cleaned


def debug_preview(label: str, value: str, *, max_chars: int = 240, **fields: Any) -> None:
    if not settings.DEBUG_PIPELINE_LOGS:
        return
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    log_event(
        "debug",
        label,
        chars=len(value),
        sha256=digest,
        preview=redacted_preview(value, max_chars=max_chars),
        **fields,
    )
