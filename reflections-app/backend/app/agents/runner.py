"""Runner — compile graphs with PostgreSQL checkpointer, expose invoke helpers."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

from app.agents.graphs.init_graph import build_init_graph
from app.agents.graphs.message_graph import build_message_graph
from app.agents.graphs.end_graph import build_end_graph
from app.database import DATABASE_URL

_conn: psycopg.Connection | None = None
_checkpointer: PostgresSaver | None = None
_init_graph = None
_message_graph = None
_end_graph = None


def setup_checkpointer() -> None:
    """Create checkpoint tables and compile graphs. Called once at app startup."""
    global _conn, _checkpointer, _init_graph, _message_graph, _end_graph

    # PostgresSaver expects a plain postgresql:// URL (not the +psycopg SQLAlchemy variant)
    sync_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")

    # Checkpoint migrations create concurrent indexes; they require autocommit.
    # None disables prepared statements for transaction-mode poolers.
    _conn = psycopg.connect(sync_url, prepare_threshold=None, autocommit=True, row_factory=dict_row)
    _checkpointer = PostgresSaver(_conn)
    _checkpointer.setup()

    _init_graph = build_init_graph().compile(checkpointer=_checkpointer)
    _message_graph = build_message_graph().compile(checkpointer=_checkpointer)
    _end_graph = build_end_graph().compile(checkpointer=_checkpointer)


def teardown_checkpointer() -> None:
    """Close the PostgresSaver connection. Called once at app shutdown."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def _thread_config(session_id: str, db=None) -> dict:
    cfg: dict = {"configurable": {"thread_id": session_id}}
    if db is not None:
        cfg["configurable"]["db"] = db
    return cfg


def invoke_start(session_id: str, student_id: str, module_id: str, db) -> dict:
    return _init_graph.invoke(
        {
            "session_id": session_id,
            "student_id": student_id,
            "module_id": module_id,
        },
        config=_thread_config(session_id, db),
    )


def invoke_message(session_id: str, user_message: str) -> dict:
    return _message_graph.invoke(
        {"user_message": user_message},
        config=_thread_config(session_id),
    )


def invoke_end(session_id: str, db) -> dict:
    return _end_graph.invoke(
        {},
        config=_thread_config(session_id, db),
    )


def platform_state(session_id: str) -> dict:
    return _message_graph.get_state(_thread_config(session_id)).values


def platform_resume_start(session_id: str, db) -> dict:
    cfg = _thread_config(session_id, db)
    checkpoint = _init_graph.get_state(cfg)
    return _init_graph.invoke(None, config=cfg) if checkpoint.next else checkpoint.values


def platform_message(session_id: str, message: str, request_id: str) -> dict:
    from fastapi import HTTPException
    cfg = _thread_config(session_id)
    checkpoint = _message_graph.get_state(cfg)
    if not checkpoint.values:
        raise HTTPException(404, "Session not found")
    if checkpoint.values.get("platform_request_id") == request_id:
        return _message_graph.invoke(None, config=cfg) if checkpoint.next else checkpoint.values
    if checkpoint.values.get("phase") == "ended":
        raise HTTPException(409, "Session has ended")
    return _message_graph.invoke({"user_message": message, "platform_request_id": request_id}, config=cfg)


def platform_end(session_id: str, db) -> dict:
    from fastapi import HTTPException
    cfg = _thread_config(session_id, db)
    checkpoint = _end_graph.get_state(cfg)
    if not checkpoint.values:
        raise HTTPException(404, "Session not found")
    if checkpoint.values.get("evaluation") is not None and checkpoint.values.get("phase") == "ended":
        return checkpoint.values
    if checkpoint.values.get("phase") == "ended" and checkpoint.next:
        return _end_graph.invoke(None, config=cfg)
    return invoke_end(session_id, db)
