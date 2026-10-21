from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas import ChatMessage
from app.term_resolution import candidate_terms, extract_definition_term, resolve_term


class TermResolutionTests(unittest.TestCase):
    def test_extracts_single_term_definition_requests(self) -> None:
        self.assertEqual(extract_definition_term("I don't know what the PATL is"), "PATL")
        self.assertEqual(extract_definition_term("what is PATL?"), "PATL")
        self.assertIsNone(extract_definition_term("what is version control?"))

    def test_candidates_include_transposition_from_history_and_documents(self) -> None:
        history = [ChatMessage(role="assistant", content="Ask the reviewer to PTAL after updating the patch.")]
        candidates = candidate_terms("PATL", history, ["portal", "PTAL", "patch"])
        self.assertEqual(candidates[0], "PTAL")
        self.assertNotIn("portal", candidates)

    def test_qwen_selects_only_a_verified_candidate(self) -> None:
        history = [ChatMessage(role="assistant", content="Ask the reviewer to PTAL after updating the patch.")]
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "decision": "corrected",
            "selected_term": "PTAL",
            "confidence": 0.96,
            "reason": "The recent review instruction used PTAL.",
        })))])

        with patch("app.term_resolution.db.published_document_terms", return_value=["PTAL", "LGTM"]), patch(
            "app.term_resolution.settings.llm_client_config",
            return_value=("Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"),
        ), patch("app.term_resolution.chat_completion", new=AsyncMock(return_value=response)) as completion:
            result = asyncio.run(resolve_term(
                "I don't know what the PATL is", history, "course-1", "conversation-1",
            ))

        self.assertIsNotNone(result)
        self.assertEqual(result.original_term, "PATL")
        self.assertEqual(result.selected_term, "PTAL")
        request = completion.await_args.args[2]
        self.assertIn("Verified candidates: PTAL", request["messages"][1]["content"])
        self.assertEqual(request["temperature"], 0)

    def test_model_invention_falls_back_to_one_document_verified_candidate(self) -> None:
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "decision": "corrected",
            "selected_term": "MADEUP",
            "confidence": 0.99,
            "reason": "Invented value.",
        })))])
        with patch("app.term_resolution.db.published_document_terms", return_value=["PTAL"]), patch(
            "app.term_resolution.settings.llm_client_config",
            return_value=("Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"),
        ), patch("app.term_resolution.chat_completion", new=AsyncMock(return_value=response)):
            result = asyncio.run(resolve_term(
                "what is PATL?", [], "course-1", "conversation-1",
            ))

        self.assertIsNotNone(result)
        self.assertEqual(result.selected_term, "PTAL")
        self.assertEqual(result.source, "python_verified")

    def test_model_invention_is_rejected_when_multiple_candidates_are_plausible(self) -> None:
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "decision": "corrected",
            "selected_term": "MADEUP",
            "confidence": 0.99,
            "reason": "Invented value.",
        })))])
        with patch("app.term_resolution.db.published_document_terms", return_value=["PTAL", "PALT"]), patch(
            "app.term_resolution.settings.llm_client_config",
            return_value=("Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"),
        ), patch("app.term_resolution.chat_completion", new=AsyncMock(return_value=response)):
            result = asyncio.run(resolve_term(
                "what is PATL?", [], "course-1", "conversation-1",
            ))

        self.assertIsNone(result)

    def test_assignment_vocabulary_uses_only_frozen_document_terms(self) -> None:
        with patch("app.term_resolution.db.published_document_terms") as terms:
            result = asyncio.run(resolve_term(
                "what is PATL?", [], None, "attempt-1", document_terms=[],
            ))
        self.assertIsNone(result)
        terms.assert_not_called()


if __name__ == "__main__":
    unittest.main()
