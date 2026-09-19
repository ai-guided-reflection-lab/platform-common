from __future__ import annotations

import unittest
from unittest.mock import patch

from app import pipeline_logging


class PipelineLoggingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
