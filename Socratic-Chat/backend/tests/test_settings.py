from __future__ import annotations

import unittest
from unittest.mock import patch

from app import settings


class LlmProviderConfigTests(unittest.TestCase):
    def test_local_qwen_roles_and_visible_output_parameters(self) -> None:
        with (
            patch.object(settings, "LLM_PROVIDER", "ollama"),
            patch.object(settings, "OLLAMA_MODEL", "qwen3.5:9b-q4_K_M"),
            patch.object(settings, "OLLAMA_CLASSIFIER_MODEL", ""),
            patch.object(settings, "OLLAMA_ANSWER_EVALUATION_MODEL", ""),
        ):
            for role in ("generation", "classifier", "evaluation"):
                config = settings.llm_client_config(role)
                self.assertEqual(config[0], "Ollama")
                self.assertEqual(config[3], "qwen3.5:9b-q4_K_M")
            self.assertEqual(settings.completion_token_parameters("Ollama", 600),
                             {"max_tokens": 600, "reasoning_effort": "none"})

    def test_embeddings_stay_on_openai_when_chat_uses_groq(self) -> None:
        with (
            patch.object(settings, "LLM_PROVIDER", "groq"),
            patch.object(settings, "OPENAI_API_KEY", "embedding-test-key"),
            patch.object(settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
            patch.object(settings, "EMBEDDING_MODEL", "text-embedding-3-small"),
        ):
            self.assertEqual(settings.embedding_client_config(), (
                "OpenAI", "embedding-test-key", "https://api.openai.com/v1",
                "text-embedding-3-small",
            ))
            self.assertEqual(settings.embedding_model_name(), "text-embedding-3-small")

    def test_missing_openai_key_does_not_fall_back_to_chat_embeddings(self) -> None:
        with patch.object(settings, "OPENAI_API_KEY", ""), patch.object(settings, "GROQ_API_KEY", "groq-test-key"):
            self.assertIsNone(settings.embedding_client_config())

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
