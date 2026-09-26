from __future__ import annotations

import unittest
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import db, main, pipeline_logging, settings
from app.schemas import ChatResponse


class PipelineDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for replacement in (
            patch.object(settings, "PIPELINE_TRACE_FILE", Path(directory.name) / "traces.json"),
            patch.object(settings, "DATABASE_URL", ""),
            patch.object(settings, "DEBUG_PIPELINE_LOGS", True),
            patch.object(settings, "RESTRICTED_SCHOOL_AUTH_ENABLED", False),
            patch.object(pipeline_logging, "_recent_traces", deque(maxlen=100)),
            patch.object(pipeline_logging, "_trace_records", {}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_fresh_clients_restore_persisted_trace_and_delete_stays_deleted(self) -> None:
        tokens = pipeline_logging.begin_trace("refresh-api", "conversation")
        pipeline_logging.log_event(12, "response_returned", sources=2)
        pipeline_logging.end_trace(tokens)
        pipeline_logging._recent_traces.clear()
        pipeline_logging._trace_records.clear()
        for _ in range(2):
            with TestClient(main.app) as client:
                response = client.get("/api/debug/pipeline/traces?limit=50")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.json()["traces"][0]["trace_id"], "refresh-api")
        response = self.client.delete("/api/debug/pipeline/traces")
        self.assertEqual(response.json(), {"deleted": 1})
        self.assertEqual(self.client.get("/api/debug/pipeline/traces").json(), {"traces": []})

    def test_disabled_diagnostics_remain_unavailable(self) -> None:
        with patch.object(settings, "DEBUG_PIPELINE_LOGS", False):
            for method in ("get", "delete"):
                self.assertEqual(getattr(self.client, method)("/api/debug/pipeline/traces").status_code, 404)

    def test_chat_and_stream_generate_traces_that_survive_fresh_reads(self) -> None:
        for route in ("/api/chat", "/api/chat/stream"):
            with self.subTest(route=route):
                pipeline_logging.delete_recent_traces()
                with (
                    patch.object(main, "_run_chat_pipeline", new_callable=AsyncMock) as generate,
                    patch.object(settings, "DEBUG_PIPELINE_LOGS", False),
                ):
                    generate.return_value = ChatResponse(answer="Generated answer", conversation_id="new-conversation")
                    response = self.client.post(route, json={"message": "Private learner message"})
                self.assertEqual(response.status_code, 200)
                generate.assert_awaited_once()
                first = self.client.get("/api/debug/pipeline/traces").json()["traces"]
                self.assertEqual(len(first), 1)
                self.assertEqual(first[0]["conversation_id"], "new-conversation")
                self.assertEqual(first[0]["events"][-1]["event"], "response_returned")
                self.assertNotIn("Private learner message", str(first))
                self.assertNotIn("Generated answer", str(first))
                pipeline_logging._recent_traces.clear()
                pipeline_logging._trace_records.clear()
                restored = self.client.get("/api/debug/pipeline/traces").json()["traces"]
                self.assertEqual(restored, first)

    def test_restricted_diagnostics_require_authentication_for_read_and_delete(self) -> None:
        with patch.object(settings, "RESTRICTED_SCHOOL_AUTH_ENABLED", True):
            for method in ("get", "delete"):
                self.assertEqual(getattr(self.client, method)("/api/debug/pipeline/traces").status_code, 401)

    def test_storage_errors_are_503_not_success_or_empty_results(self) -> None:
        with (
            patch.object(db, "get_pipeline_traces", side_effect=RuntimeError("offline")),
            patch.object(db, "delete_pipeline_traces", side_effect=RuntimeError("offline")),
            self.assertLogs("app.pipeline", level="WARNING"),
        ):
            for method in ("get", "delete"):
                self.assertEqual(getattr(self.client, method)("/api/debug/pipeline/traces").status_code, 503)
