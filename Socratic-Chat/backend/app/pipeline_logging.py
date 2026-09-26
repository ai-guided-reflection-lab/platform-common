from __future__ import annotations

from contextvars import ContextVar, Token
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from time import monotonic
from threading import RLock
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
_recent_traces: deque[dict[str, Any]] = deque(maxlen=100)
_trace_records: dict[str, dict[str, Any]] = {}
_trace_lock = RLock()

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


def begin_trace(trace_id: str, conversation_id: str | None = None) -> tuple[Token, Token, Token]:
    with _trace_lock:
        _trace_records[trace_id] = {
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "events": [],
        }
        _recent_traces.append(_trace_records[trace_id])
        retained_ids = {record["trace_id"] for record in _recent_traces}
        for retained_trace_id in tuple(_trace_records):
            if retained_trace_id not in retained_ids:
                del _trace_records[retained_trace_id]
    return (
        _trace_id.set(trace_id),
        _conversation_id.set(conversation_id),
        _trace_started_at.set(monotonic()),
    )


def end_trace(tokens: tuple[Token, Token, Token]) -> None:
    trace_id = _trace_id.get()
    if trace_id:
        _persist_trace(trace_id)
    trace_token, conversation_token, started_token = tokens
    _trace_started_at.reset(started_token)
    _conversation_id.reset(conversation_token)
    _trace_id.reset(trace_token)


def set_conversation_id(conversation_id: str | None) -> None:
    _conversation_id.set(conversation_id)
    with _trace_lock:
        record = _trace_records.get(_trace_id.get())
        if record is not None:
            record["conversation_id"] = conversation_id


def trace_active() -> bool:
    return _trace_id.get() is not None


def publish_event(event: str, **fields: Any) -> None:
    sink = _event_sink.get()
    if sink is not None:
        sink(event, fields)


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
    with _trace_lock:
        trace_record = _trace_records.get(trace_id)
        if trace_record is not None:
            trace_record["events"].append(
                {
                    "stage": stage,
                    "event": event,
                    "elapsed_ms": values["elapsed_ms"],
                    "fields": _safe_trace_fields(fields),
                }
            )
            _persist_trace(trace_id)
    sink = _event_sink.get()
    if sink is not None:
        sink(event, fields)


def _safe_trace_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Keep the trace viewer useful without retaining full prompt or answer text."""
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if key in {"preview", "path"}:
            safe[key] = redacted_preview(str(value), max_chars=160) if key == "preview" else str(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple)):
            safe[key] = [str(item) for item in value[:10]]
        else:
            safe[key] = str(value)
    return safe


def recent_traces(limit: int = 25) -> list[dict[str, Any]]:
    """Merge persisted and live traces; an older store must not hide live work."""
    bounded_limit = min(max(limit, 1), 100)
    traces: dict[str, dict[str, Any]] = {}
    errors = []
    try:
        from app import db
        for trace in db.get_pipeline_traces(100):
            traces[trace["trace_id"]] = trace
    except Exception as error:
        LOGGER.warning("Unable to load pipeline traces from database: %s", error)
        errors.append(error)
    with _trace_lock:
        try:
            for trace in _read_trace_file():
                previous = traces.get(trace["trace_id"])
                if previous is None or len(trace["events"]) > len(previous["events"]):
                    traces[trace["trace_id"]] = trace
        except (OSError, ValueError) as error:
            LOGGER.warning("Unable to load persisted pipeline traces: %s", error)
            errors.append(error)
        for trace in _recent_traces:
            previous = traces.get(trace["trace_id"])
            if previous is None or len(trace["events"]) >= len(previous["events"]):
                traces[trace["trace_id"]] = deepcopy(trace)
    if not traces and errors:
        raise RuntimeError("Unable to load stored pipeline traces. Check the server logs.") from errors[0]
    return sorted(traces.values(), key=lambda trace: trace["started_at"], reverse=True)[:bounded_limit]


def _read_trace_file() -> list[dict[str, Any]]:
    trace_file = settings.PIPELINE_TRACE_FILE
    if not trace_file or not trace_file.exists():
        return []
    traces = json.loads(trace_file.read_text(encoding="utf-8"))
    if not isinstance(traces, list) or any(
        not isinstance(trace, dict)
        or not isinstance(trace.get("trace_id"), str)
        or not isinstance(trace.get("started_at"), str)
        or not isinstance(trace.get("events"), list)
        for trace in traces
    ):
        raise ValueError(f"Invalid pipeline trace file: {trace_file}")
    return traces


def delete_recent_traces() -> int:
    with _trace_lock:
        deleted = 0
        errors = []
        try:
            from app import db
            deleted = db.delete_pipeline_traces()
        except Exception as error:
            LOGGER.warning("Unable to delete pipeline traces from database: %s", error)
            errors.append(error)
        retained_ids = {trace["trace_id"] for trace in _recent_traces}
        trace_file = settings.PIPELINE_TRACE_FILE
        if trace_file and trace_file.exists():
            try:
                try:
                    retained_ids.update(trace["trace_id"] for trace in _read_trace_file())
                except ValueError as error:
                    LOGGER.warning("Deleting invalid pipeline trace file: %s", error)
                trace_file.unlink()
            except OSError as error:
                LOGGER.warning("Unable to delete pipeline trace file %s: %s", trace_file, error)
                errors.append(error)
        _recent_traces.clear()
        _trace_records.clear()
        if errors:
            raise RuntimeError("Unable to delete all stored pipeline traces. Please retry.") from errors[0]
        return max(deleted, len(retained_ids))


def _persist_trace(trace_id: str) -> None:
    with _trace_lock:
        _persist_trace_locked(trace_id)


def _persist_trace_locked(trace_id: str) -> None:
    trace = _trace_records.get(trace_id)
    if trace:
        try:
            from app import db
            db.save_pipeline_trace(trace)
        except Exception as error:
            LOGGER.warning("Unable to persist pipeline trace %s to database: %s", trace_id, error)
    trace_file = settings.PIPELINE_TRACE_FILE
    if not trace or not trace_file:
        return
    try:
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_trace_file()
        existing = [item for item in existing if item.get("trace_id") != trace_id]
        existing.append(trace)
        existing.sort(key=lambda item: item["started_at"])
        temporary = trace_file.with_suffix(".tmp")
        temporary.touch(mode=0o600, exist_ok=True)
        temporary.chmod(0o600)
        temporary.write_text(json.dumps(existing[-100:], ensure_ascii=True) + "\n", encoding="utf-8")
        temporary.replace(trace_file)
    except (OSError, TypeError, ValueError) as error:
        LOGGER.warning("Unable to persist pipeline trace %s: %s", trace_id, error)


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
