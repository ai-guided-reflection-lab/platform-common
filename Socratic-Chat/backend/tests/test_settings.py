from __future__ import annotations

import unittest
from unittest.mock import patch

from app import settings


class LlmProviderConfigTests(unittest.TestCase):
    def test_groq_chat_configuration_is_separate_from_openai_embeddings(self) -> None:
        with (
            patch.object(settings, "LLM_PROVIDER", "groq"),
            patch.object(settings, "GROQ_API_KEY", "groq-test-key"),
            patch.object(settings, "GROQ_API_BASE_URL", "https://api.groq.com/openai/v1"),
            patch.object(settings, "GROQ_MODEL", "openai/gpt-oss-120b"),
            patch.object(settings, "OPENAI_API_KEY", "embedding-test-key"),
        ):
            config = settings.llm_client_config("generation")

        self.assertEqual(
            config,
            ("Groq", "groq-test-key", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
        )

    def test_groq_120b_is_used_for_each_conversational_role(self) -> None:
        with (
            patch.object(settings, "LLM_PROVIDER", "groq"),
            patch.object(settings, "GROQ_API_KEY", "groq-test-key"),
            patch.object(settings, "GROQ_API_BASE_URL", "https://api.groq.com/openai/v1"),
            patch.object(settings, "GROQ_MODEL", "openai/gpt-oss-120b"),
            patch.object(settings, "GROQ_CLASSIFIER_MODEL", "openai/gpt-oss-120b"),
            patch.object(settings, "GROQ_ANSWER_EVALUATION_MODEL", "openai/gpt-oss-120b"),
        ):
            for role in ("generation", "classifier", "evaluation"):
                with self.subTest(role=role):
                    self.assertEqual(
                        settings.llm_client_config(role),
                        (
                            "Groq",
                            "groq-test-key",
                            "https://api.groq.com/openai/v1",
                            "openai/gpt-oss-120b",
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
