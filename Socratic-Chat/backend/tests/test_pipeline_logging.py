from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
        self.assertIn("elapsed_ms=", output)

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


if __name__ == "__main__":
    unittest.main()
