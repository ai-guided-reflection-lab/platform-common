from __future__ import annotations

import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import settings
from app.classifier import MessageClassification
from app.rag import generate_conversation_transition


class DialogueTransitionTests(unittest.TestCase):
    def _run_with_response(self, response_text: str, action: str = "complete") -> str:
        class Completions:
            async def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))]
                )

        class FakeAsyncOpenAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=Completions())

        classification = MessageClassification(
            dialogue_status="closing" if action == "complete" else "acknowledgement",
            conversation_action=action,
            wants_to_continue=False,
            confidence=0.95,
            source="llm",
        )
        with (
            patch.object(settings, "LLM_PROVIDER", "openai"),
            patch.object(settings, "OPENAI_API_KEY", "test-key"),
            patch.dict(sys.modules, {"openai": SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)}),
        ):
            return asyncio.run(generate_conversation_transition("Nothing, bye.", [], classification))

    def test_valid_natural_closure_is_used(self) -> None:
        answer = self._run_with_response("Take care, and come back whenever you want to continue.")
        self.assertEqual(answer, "Take care, and come back whenever you want to continue.")
        self.assertNotIn("?", answer)

    def test_transition_response_is_forwarded_without_question_validation(self) -> None:
        answer = self._run_with_response("Would you like to review anything else?")
        self.assertEqual(answer, "Would you like to review anything else?")


if __name__ == "__main__":
    unittest.main()
