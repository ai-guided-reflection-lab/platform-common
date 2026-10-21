"""Durable JSON sessions. The platform serializes actions for each attempt."""
import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

from tutor import Session


class SessionStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("TUTOR_SESSION_DB", str(Path(__file__).parent / "data/sessions.sqlite3")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS operations (session_id TEXT, request_id TEXT, response TEXT NOT NULL, PRIMARY KEY(session_id, request_id))")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, session_id, default=None):
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
        return Session(**json.loads(row[0])) if row else default

    def __setitem__(self, session_id, session):
        with self.connect() as conn:
            self.save(conn, session)

    def save(self, conn, session):
        conn.execute("INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (session.session_id, json.dumps(asdict(session))))

    def pop(self, session_id, default=None):
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            conn.execute("DELETE FROM operations WHERE session_id=?", (session_id,))

    def perform(self, session_id, request_id, operation):
        # Save state and retry response atomically. BEGIN IMMEDIATE also serializes
        # standalone requests across threads/processes using this SQLite file.
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cached = conn.execute("SELECT response FROM operations WHERE session_id=? AND request_id=?", (session_id, request_id)).fetchone()
            if cached:
                return json.loads(cached[0])
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise KeyError(session_id)
            session = Session(**json.loads(row[0]))
            operation(session)
            response = session.to_public()
            self.save(conn, session)
            conn.execute("INSERT INTO operations VALUES (?, ?, ?)", (session_id, request_id, json.dumps(response)))
            return response
