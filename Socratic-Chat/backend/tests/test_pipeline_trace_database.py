"""Optional PostgreSQL regression using only a unique, disposable schema."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app import db, main, pipeline_logging, settings


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL for PostgreSQL coverage.")
class PipelineTraceDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        import psycopg
        from psycopg import sql

        dsn = os.environ["TEST_DATABASE_URL"]
        schema = "pipeline_test_" + uuid4().hex
        self.connection = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.connection.close)
        self.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.addCleanup(
            self.connection.execute,
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)),
        )
        for replacement in (
            patch.object(settings, "DATABASE_URL", dsn),
            patch.object(settings, "PLATFORM_DB_SCHEMA", schema),
            patch.object(settings, "SOCRATIC_DB_SCHEMA", schema),
            patch.object(settings, "PIPELINE_TRACE_FILE", None),
            patch.object(settings, "DEBUG_PIPELINE_LOGS", True),
            patch.object(settings, "RESTRICTED_SCHOOL_AUTH_ENABLED", False),
            patch.object(pipeline_logging, "_recent_traces", deque(maxlen=100)),
            patch.object(pipeline_logging, "_trace_records", {}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE pipeline_traces_socratic_chat (
                    trace_id TEXT PRIMARY KEY, conversation_id UUID,
                    started_at TIMESTAMPTZ NOT NULL, trace JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

    def test_real_database_checkpoint_is_visible_after_restart_then_deleted(self) -> None:
        conversation = str(uuid4())
        tokens = pipeline_logging.begin_trace("database-refresh")
        pipeline_logging.set_conversation_id(conversation)
        pipeline_logging.log_event(12, "response_returned", sources=2)
        pipeline_logging.end_trace(tokens)
        pipeline_logging._recent_traces.clear()
        pipeline_logging._trace_records.clear()
        # Do not run application startup/migrations against unrelated schemas.
        client = TestClient(main.app)
        self.addCleanup(client.close)
        response = client.get("/api/debug/pipeline/traces")
        self.assertEqual(response.status_code, 200)
        trace = response.json()["traces"][0]
        self.assertEqual(trace["trace_id"], "database-refresh")
        self.assertEqual(trace["conversation_id"], conversation)
        self.assertEqual(trace["events"][0]["event"], "response_returned")
        self.assertEqual(client.delete("/api/debug/pipeline/traces").json(), {"deleted": 1})
        self.assertEqual(client.get("/api/debug/pipeline/traces").json(), {"traces": []})

    def test_database_retains_only_latest_100_requests(self) -> None:
        started = datetime.now(timezone.utc)
        for index in range(105):
            db.save_pipeline_trace({
                "trace_id": f"trace-{index}",
                "conversation_id": None,
                "started_at": (started + timedelta(seconds=index)).isoformat(),
                "events": [],
            })
        traces = db.get_pipeline_traces(1000)
        self.assertEqual(len(traces), 100)
        self.assertEqual(traces[0]["trace_id"], "trace-104")
        self.assertEqual(traces[-1]["trace_id"], "trace-5")
        with db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM pipeline_traces_socratic_chat").fetchone()[0], 100)
