from __future__ import annotations

import unittest
import json
import os
import subprocess
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import db, pipeline_logging


class PipelineLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.trace_file = Path(directory.name) / "traces.json"
        for replacement in (
            patch.object(pipeline_logging.settings, "PIPELINE_TRACE_FILE", self.trace_file),
            patch.object(db.settings, "DATABASE_URL", ""),
            patch.object(pipeline_logging, "_recent_traces", deque(maxlen=100)),
            patch.object(pipeline_logging, "_trace_records", {}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_events_include_trace_and_updated_conversation_id(self) -> None:
        tokens = pipeline_logging.begin_trace("trace-123", None)
        try:
            with self.assertLogs("app.pipeline", level="INFO") as captured:
                pipeline_logging.log_event(1, "chat_received", message_chars=24)
                pipeline_logging.set_conversation_id("conversation-456")
                pipeline_logging.log_event(3, "history_loaded", messages=2)
        finally:
            pipeline_logging.end_trace(tokens)

        output = "\n".join(captured.output)
        self.assertIn("trace_id=trace-123", output)
        self.assertIn("conversation_id=conversation-456", output)
        self.assertIn("event=history_loaded", output)
        self.assertIn("elapsed_ms=", output)
        self.assertEqual(pipeline_logging.recent_traces()[0]["conversation_id"], "conversation-456")

    def test_recent_traces_capture_decision_fields_without_prompt_content(self) -> None:
        tokens = pipeline_logging.begin_trace("trace-viewer", "conversation-456")
        try:
            pipeline_logging.log_event(
                4,
                "message_classification_completed",
                question_type="what",
                dialogue_status="requesting_support",
                target_concepts="core skill|code review",
            )
            traces = pipeline_logging.recent_traces()
        finally:
            pipeline_logging.end_trace(tokens)

        trace = next(item for item in traces if item["trace_id"] == "trace-viewer")
        event = trace["events"][0]
        self.assertEqual(event["event"], "message_classification_completed")
        self.assertEqual(event["fields"]["question_type"], "what")
        self.assertEqual(event["fields"]["target_concepts"], "core skill|code review")

    def test_debug_logging_uses_digest_instead_of_content(self) -> None:
        sensitive_text = "student@example.edu asked a private question"
        tokens = pipeline_logging.begin_trace("trace-123", "conversation-456")
        try:
            with (
                patch.object(pipeline_logging.settings, "DEBUG_PIPELINE_LOGS", True),
                self.assertLogs("app.pipeline", level="INFO") as captured,
            ):
                pipeline_logging.debug_digest("user_message", sensitive_text)
        finally:
            pipeline_logging.end_trace(tokens)

        output = "\n".join(captured.output)
        self.assertIn("event=user_message_digest", output)
        self.assertIn("sha256=", output)
        self.assertNotIn(sensitive_text, output)

    def test_debug_preview_redacts_secrets_and_truncates_content(self) -> None:
        sensitive_text = "Email student@example.edu api_key=secret-value " + ("course material " * 30)
        tokens = pipeline_logging.begin_trace("trace-123", "conversation-456")
        try:
            with (
                patch.object(pipeline_logging.settings, "DEBUG_PIPELINE_LOGS", True),
                self.assertLogs("app.pipeline", level="INFO") as captured,
            ):
                pipeline_logging.debug_preview("retrieved_chunk", sensitive_text, max_chars=80)
        finally:
            pipeline_logging.end_trace(tokens)

        output = "\n".join(captured.output)
        self.assertIn("[redacted-email]", output)
        self.assertIn("[redacted-secret]", output)
        self.assertIn("\\u2026", output)
        self.assertNotIn("student@example.edu", output)
        self.assertNotIn("secret-value", output)

    def test_full_prompt_snapshot_preserves_exact_request_locally(self) -> None:
        request = {
            "model": "openai/gpt-oss-120b",
            "messages": [
                {"role": "system", "content": "Use the retrieved evidence."},
                {"role": "user", "content": "Why does this example matter?"},
            ],
            "temperature": 0.2,
        }
        with TemporaryDirectory() as temporary_directory:
            tokens = pipeline_logging.begin_trace("trace-prompt", "conversation-456")
            try:
                with (
                    patch.object(pipeline_logging.settings, "LOG_FULL_PROMPTS", True),
                    patch.object(pipeline_logging.settings, "PIPELINE_PROMPT_DIR", Path(temporary_directory)),
                ):
                    destination = pipeline_logging.write_llm_request_snapshot(
                        "tutor-generation", "Groq", request,
                    )
                    pipeline_logging.update_llm_request_snapshot(
                        "tutor-generation",
                        raw_response="Model draft",
                        final_response="Model answer",
                        latency_ms=1234,
                    )
            finally:
                pipeline_logging.end_trace(tokens)

            self.assertIsNotNone(destination)
            snapshot = Path(destination).read_text(encoding="utf-8")
            self.assertIn('"content": "Use the retrieved evidence."', snapshot)
            self.assertIn('"content": "Why does this example matter?"', snapshot)
            self.assertIn('"conversation_id": "conversation-456"', snapshot)
            self.assertIn('"raw_response": "Model draft"', snapshot)
            self.assertIn('"final_response": "Model answer"', snapshot)
            self.assertIn('"latency_ms": 1234', snapshot)

    def test_completed_trace_is_persisted_for_refresh_and_restart(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            trace_file = Path(temporary_directory) / "traces.json"
            with patch.object(pipeline_logging.settings, "PIPELINE_TRACE_FILE", trace_file):
                tokens = pipeline_logging.begin_trace("trace-persisted", "conversation-456")
                pipeline_logging.log_event(12, "response_returned", sources=2)
                pipeline_logging.end_trace(tokens)

                pipeline_logging._recent_traces.clear()
                pipeline_logging._trace_records.clear()
                traces = pipeline_logging.recent_traces()

            trace = next(item for item in traces if item["trace_id"] == "trace-persisted")
            self.assertEqual(trace["events"][0]["event"], "response_returned")
            self.assertTrue(trace_file.exists())

    def test_trace_is_checkpointed_before_request_finishes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            trace_file = Path(temporary_directory) / "traces.json"
            with patch.object(pipeline_logging.settings, "PIPELINE_TRACE_FILE", trace_file):
                tokens = pipeline_logging.begin_trace("trace-checkpoint", "conversation-456")
                pipeline_logging.log_event(4, "message_classification_completed", confidence=0.95)
                persisted = trace_file.read_text(encoding="utf-8")
                pipeline_logging.end_trace(tokens)

            self.assertIn("message_classification_completed", persisted)

    def _record(self, trace_id: str) -> None:
        tokens = pipeline_logging.begin_trace(trace_id)
        try:
            pipeline_logging.log_event(12, "response_returned", sources=2)
        finally:
            pipeline_logging.end_trace(tokens)

    def test_old_database_records_do_not_hide_new_file_or_live_traces(self) -> None:
        self._record("old")
        database_trace = json.loads(self.trace_file.read_text())[0]
        self._record("new-file")
        pipeline_logging._recent_traces.clear()
        pipeline_logging._trace_records.clear()
        with patch.object(db, "get_pipeline_traces", return_value=[database_trace]):
            self._record("new-live")
            self.assertEqual(
                [trace["trace_id"] for trace in pipeline_logging.recent_traces(2)],
                ["new-live", "new-file"],
            )

    def test_latest_checkpoint_wins_without_duplicate_trace(self) -> None:
        self._record("one")
        stale = json.loads(self.trace_file.read_text())[0]
        stale["events"] = []
        with patch.object(db, "get_pipeline_traces", return_value=[stale]):
            traces = pipeline_logging.recent_traces()
        self.assertEqual(len(traces), 1)
        self.assertEqual(len(traces[0]["events"]), 1)

    def test_concurrent_traces_are_retained_across_restart(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(self._record, [f"trace-{index}" for index in range(12)]))
        pipeline_logging._recent_traces.clear()
        pipeline_logging._trace_records.clear()
        self.assertEqual(len(pipeline_logging.recent_traces()), 12)
        self.assertEqual(self.trace_file.stat().st_mode & 0o777, 0o600)

    def test_file_can_be_read_by_a_new_python_process(self) -> None:
        self._record("previous-process")
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import json; from app.pipeline_logging import recent_traces; "
                "print(json.dumps(recent_traces()))",
            ],
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                "DATABASE_URL": "",
                "PIPELINE_TRACE_FILE": str(self.trace_file),
                "PIPELINE_LOG_FILE": "",
            },
            check=True, capture_output=True, text=True,
        )
        restored = json.loads(result.stdout)
        self.assertEqual(restored[0]["trace_id"], "previous-process")
        self.assertEqual(restored[0]["events"][0]["event"], "response_returned")

    def test_retention_and_delete_survive_restart_and_request_completion(self) -> None:
        for index in range(105):
            self._record(f"trace-{index}")
        self.assertEqual(len(json.loads(self.trace_file.read_text())), 100)
        self.assertEqual(len(pipeline_logging.recent_traces(1000)), 100)
        tokens = pipeline_logging.begin_trace("in-progress")
        pipeline_logging.log_event(1, "chat_received")
        self.assertEqual(pipeline_logging.delete_recent_traces(), 100)
        pipeline_logging.log_event(12, "response_returned")
        pipeline_logging.end_trace(tokens)
        self.assertFalse(self.trace_file.exists())
        self.assertEqual(pipeline_logging.recent_traces(), [])

    def test_unreadable_storage_is_not_reported_as_no_traces(self) -> None:
        self.trace_file.write_text("{}")
        with self.assertLogs("app.pipeline", level="WARNING"), self.assertRaises(RuntimeError):
            pipeline_logging.recent_traces()

    def test_database_failure_uses_file_but_failed_delete_is_explicit(self) -> None:
        self._record("retained")
        with (
            patch.object(db, "get_pipeline_traces", side_effect=RuntimeError("offline")),
            self.assertLogs("app.pipeline", level="WARNING"),
        ):
            self.assertEqual(pipeline_logging.recent_traces()[0]["trace_id"], "retained")
        with (
            patch.object(db, "delete_pipeline_traces", side_effect=RuntimeError("offline")),
            self.assertLogs("app.pipeline", level="WARNING"),
            self.assertRaises(RuntimeError),
        ):
            pipeline_logging.delete_recent_traces()


if __name__ == "__main__":
    unittest.main()
