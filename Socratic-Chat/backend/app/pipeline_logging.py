from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from time import monotonic
import re
import sys
from typing import Any, Callable

from app import settings


LOGGER = logging.getLogger("app.pipeline")
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    if settings.PIPELINE_LOG_FILE:
        settings.PIPELINE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.PIPELINE_LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOGGER.addHandler(file_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

_trace_id: ContextVar[str | None] = ContextVar("pipeline_trace_id", default=None)
_conversation_id: ContextVar[str | None] = ContextVar("pipeline_conversation_id", default=None)
_trace_started_at: ContextVar[float | None] = ContextVar("pipeline_trace_started_at", default=None)
_event_sink: ContextVar[Callable[[str, dict[str, Any]], None] | None] = ContextVar(
    "pipeline_event_sink", default=None,
)

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


def begin_trace(trace_id: str, conversation_id: str | None = None) -> tuple[Token, Token, Token]:
    return (
        _trace_id.set(trace_id),
        _conversation_id.set(conversation_id),
        _trace_started_at.set(monotonic()),
    )


def end_trace(tokens: tuple[Token, Token, Token]) -> None:
    trace_token, conversation_token, started_token = tokens
    _trace_started_at.reset(started_token)
    _conversation_id.reset(conversation_token)
    _trace_id.reset(trace_token)


def set_conversation_id(conversation_id: str | None) -> None:
    _conversation_id.set(conversation_id)


def trace_active() -> bool:
    return _trace_id.get() is not None


def set_event_sink(sink: Callable[[str, dict[str, Any]], None]) -> Token:
    """Forward this request's pipeline events to a live progress stream."""
    return _event_sink.set(sink)


def reset_event_sink(token: Token) -> None:
    _event_sink.reset(token)


def _elapsed_ms() -> int:
    started_at = _trace_started_at.get()
    return round((monotonic() - started_at) * 1000) if started_at is not None else 0


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
        "elapsed_ms": _elapsed_ms(),
        **fields,
    }
    LOGGER.log(level, " ".join(f"{key}={_field(value)}" for key, value in values.items()))
    sink = _event_sink.get()
    if sink is not None:
        sink(event, fields)


def log_exception(stage: int | str, event: str, error: BaseException, **fields: Any) -> None:
    trace_id = _trace_id.get()
    if not trace_id:
        return
    values = {
        "trace_id": trace_id,
        "conversation_id": _conversation_id.get(),
        "stage": stage,
        "event": event,
        "elapsed_ms": _elapsed_ms(),
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


def write_llm_request_snapshot(phase: str, provider: str, request: dict[str, Any]) -> str | None:
    """Save the exact local LLM request for inspection when explicitly enabled."""
    trace_id = _trace_id.get()
    if not settings.LOG_FULL_PROMPTS or not trace_id or not settings.PIPELINE_PROMPT_DIR:
        return None

    safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]", "_", trace_id)
    safe_phase = re.sub(r"[^a-zA-Z0-9_-]", "_", phase)
    settings.PIPELINE_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    destination = settings.PIPELINE_PROMPT_DIR / f"{safe_trace_id}-{safe_phase}.json"
    snapshot = {
        "trace_id": trace_id,
        "conversation_id": _conversation_id.get(),
        "phase": phase,
        "provider": provider,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "request": request,
    }
    destination.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    destination.chmod(0o600)
    log_event(
        "debug",
        "full_prompt_saved",
        phase=phase,
        path=str(destination),
        messages=len(request.get("messages", [])),
    )
    return str(destination)


def update_llm_request_snapshot(phase: str, **result: Any) -> str | None:
    """Attach the exact model result and pipeline interpretation to a saved request."""
    trace_id = _trace_id.get()
    if not settings.LOG_FULL_PROMPTS or not trace_id or not settings.PIPELINE_PROMPT_DIR:
        return None

    safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]", "_", trace_id)
    safe_phase = re.sub(r"[^a-zA-Z0-9_-]", "_", phase)
    destination = settings.PIPELINE_PROMPT_DIR / f"{safe_trace_id}-{safe_phase}.json"
    if not destination.exists():
        return None

    snapshot = json.loads(destination.read_text(encoding="utf-8"))
    snapshot.setdefault("result", {}).update(result)
    snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(destination)
    destination.chmod(0o600)
    log_event("debug", "full_model_result_saved", phase=phase, path=str(destination))
    return str(destination)
