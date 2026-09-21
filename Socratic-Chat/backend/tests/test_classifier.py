from __future__ import annotations

import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import classifier, settings
from app.classifier import MessageClassification, classify_message
from app.schemas import ChatMessage


class MessageClassifierTests(unittest.TestCase):
    def classify_with_rules(
        self, message: str, history: list[ChatMessage] | None = None,
    ) -> MessageClassification:
        with patch.object(settings, "CLASSIFIER_ENABLED", False):
            return asyncio.run(classify_message(message, history or []))

    def test_extracts_clean_concept_from_explain_what_question(self) -> None:
        result = self.classify_with_rules("Explain what GitHub is.")
        self.assertEqual(result.route, "learning")
        self.assertEqual(result.student_intent, "definition")
        self.assertEqual(result.target_concepts, ("GitHub",))
        self.assertEqual(result.target, "GitHub")

    def test_administrative_questions_are_protected_by_rules(self) -> None:
        result = self.classify_with_rules("What are the Assignment 4 submission requirements?")
        self.assertEqual(result.route, "administrative")
        self.assertEqual(result.student_intent, "administrative")
        self.assertFalse(result.needs_clarification)

    def test_follow_up_resolves_the_recent_course_concept(self) -> None:
        history = [
            ChatMessage(role="user", content="What is version control?"),
            ChatMessage(role="assistant", content="Imagine two developers edit one file. What problem might appear?"),
        ]
        result = self.classify_with_rules("Why is that important?", history)
        self.assertEqual(result.target_concepts, ("version control",))
        self.assertIn("version control", result.rewritten_query or "")

    def test_natural_comparison_question_finds_both_concepts(self) -> None:
        result = self.classify_with_rules("How are Git and GitHub different?")
        self.assertEqual(result.student_intent, "comparison")
        self.assertEqual(result.question_type, "comparison")
        self.assertEqual(result.target_concepts, ("Git", "GitHub"))

    def test_short_ambiguous_message_requests_clarification(self) -> None:
        result = self.classify_with_rules("configuration")
        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.route, "unclear")
        self.assertIn("course concept", result.clarification_question or "")

    def test_llm_output_is_validated_and_used_for_learning_message(self) -> None:
        payload = """{
            "route": "learning",
            "student_intent": "comparison",
            "question_type": "comparison",
            "target_concepts": ["Git", "GitHub"],
            "conversation_state": "new_concept",
            "confidence": 0.94,
            "needs_clarification": false,
            "clarification_question": null,
            "retrieval_query": "Git GitHub differences"
        }"""

        class Completions:
            async def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
                )

        class FakeAsyncOpenAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=Completions())

        with (
            patch.object(settings, "CLASSIFIER_ENABLED", True),
            patch.object(settings, "LLM_PROVIDER", "openai"),
            patch.object(settings, "OPENAI_API_KEY", "test-key"),
            patch.dict(sys.modules, {"openai": SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)}),
        ):
            result = asyncio.run(classify_message("How are Git and GitHub different?", []))

        self.assertEqual(result.source, "llm")
        self.assertEqual(result.student_intent, "comparison")
        self.assertEqual(result.target_concepts, ("Git", "GitHub"))
        self.assertEqual(result.rewritten_query, "Git GitHub differences")

    def test_invalid_llm_output_falls_back_to_rules(self) -> None:
        class Completions:
            async def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
                )

        class FakeAsyncOpenAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=Completions())

        with (
            patch.object(settings, "CLASSIFIER_ENABLED", True),
            patch.object(settings, "LLM_PROVIDER", "openai"),
            patch.object(settings, "OPENAI_API_KEY", "test-key"),
            patch.dict(sys.modules, {"openai": SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)}),
        ):
            result = asyncio.run(classify_message("What is version control?", []))

        self.assertEqual(result.source, "rules")
        self.assertEqual(result.target_concepts, ("version control",))

    def test_llm_routes_a_bare_understanding_claim_to_verification(self) -> None:
        fallback = classifier._rule_classification("I understand it.", [])
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "student_intent": "comprehension_claim",
                "question_type": "statement",
                "target_concepts": ["version control"],
                "conversation_state": "claiming_understanding",
                "dialogue_status": "claiming_understanding",
                "conversation_action": "verify_understanding",
                "has_substantive_claim": False,
                "student_claim": None,
                "wants_to_continue": True,
                "confidence": 0.95,
                "needs_clarification": False,
                "retrieval_query": "version control",
            },
            "I understand it.",
            fallback,
        )
        self.assertEqual(result.conversation_action, "verify_understanding")
        self.assertFalse(result.has_substantive_claim)

    def test_llm_cannot_turn_ordinary_definition_into_direct_answer(self) -> None:
        message = "what is the code review"
        fallback = classifier._rule_classification(message, [])
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "student_intent": "direct_answer",
                "question_type": "what",
                "target_concepts": ["code review"],
                "conversation_state": "requesting_answer",
                "dialogue_status": "answering_tutor",
                "conversation_action": "direct",
                "confidence": 0.95,
                "needs_clarification": False,
                "retrieval_query": "code review",
            },
            message,
            fallback,
        )
        self.assertEqual(result.student_intent, "definition")
        self.assertEqual(result.conversation_state, "new_concept")
        self.assertEqual(result.conversation_action, "continue")

    def test_llm_routes_a_substantive_confirmation_request_to_claim_check(self) -> None:
        message = "I think Git and GitHub are the same. Is that correct?"
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "student_intent": "confirmation",
                "question_type": "follow_up",
                "target_concepts": ["Git", "GitHub"],
                "conversation_state": "possible_misconception",
                "dialogue_status": "requesting_confirmation",
                "conversation_action": "verify_claim",
                "has_substantive_claim": True,
                "student_claim": "Git and GitHub are the same.",
                "wants_to_continue": True,
                "confidence": 0.97,
                "needs_clarification": False,
                "retrieval_query": "Git and GitHub relationship",
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.conversation_action, "verify_claim")
        self.assertTrue(result.has_substantive_claim)
        self.assertEqual(result.student_claim, "Git and GitHub are the same.")

    def test_llm_cannot_treat_plain_student_answer_as_confirmation_request(self) -> None:
        message = "It reduces code conflicts in a team."
        fallback = classifier._rule_classification(
            message,
            [ChatMessage(role="assistant", content="What problem might version control help solve?")],
        )
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "student_intent": "confirmation",
                "question_type": "statement",
                "target_concepts": ["version control"],
                "conversation_state": "possible_misconception",
                "dialogue_status": "requesting_confirmation",
                "conversation_action": "verify_claim",
                "has_substantive_claim": True,
                "student_claim": "Version control reduces code conflicts.",
                "confidence": 0.97,
                "needs_clarification": False,
                "retrieval_query": "version control code conflicts",
            },
            message,
            fallback,
        )
        self.assertEqual(result.dialogue_status, "answering_tutor")
        self.assertEqual(result.conversation_action, "continue")

    def test_low_confidence_completion_is_softened(self) -> None:
        message = "Thanks, I think that is enough."
        result = classifier._validated_llm_classification(
            {
                "dialogue_status": "closing",
                "conversation_action": "complete",
                "wants_to_continue": False,
                "confidence": 0.62,
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.conversation_action, "soft_close")
        self.assertFalse(result.wants_to_continue)

    def test_llm_can_explicitly_classify_document_listing_request(self) -> None:
        message = "Which documents are currently published for this course?"
        result = classifier._validated_llm_classification(
            {
                "route": "administrative",
                "student_intent": "administrative",
                "question_type": "what",
                "operational_request": "list_documents",
                "confidence": 0.98,
                "needs_clarification": False,
                "retrieval_query": message,
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.operational_request, "list_documents")

    def test_learning_statement_keeps_operational_request_none(self) -> None:
        message = (
            "Code annotations align with lines rather than merely connecting with files "
            "that other developers have generated."
        )
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "student_intent": "reflection",
                "question_type": "statement",
                "conversation_state": "follow_up",
                "dialogue_status": "unclear",
                "conversation_action": "continue",
                "operational_request": "none",
                "confidence": 0.95,
                "needs_clarification": False,
                "retrieval_query": "code annotations lines format",
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.route, "learning")
        self.assertEqual(result.operational_request, "none")

    def test_llm_classifies_understanding_and_repeated_support_need(self) -> None:
        message = "I still do not understand code review."
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "student_intent": "hint",
                "question_type": "statement",
                "target_concepts": ["code review"],
                "conversation_state": "uncertain",
                "dialogue_status": "uncertain",
                "conversation_action": "continue",
                "understanding_level": "beginner",
                "support_level": 2,
                "confidence": 0.96,
                "needs_clarification": False,
                "retrieval_query": "code review purpose process",
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.understanding_level, "beginner")
        self.assertEqual(result.support_level, 2)


if __name__ == "__main__":
    unittest.main()
