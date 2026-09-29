from __future__ import annotations

import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import classifier, settings
from app.answer_evaluation import should_evaluate_answer
from app.classifier import MessageClassification, classify_message
from app.schemas import ChatMessage


class MessageClassifierTests(unittest.TestCase):
    def test_new_concept_question_cannot_become_administrative(self) -> None:
        message = "what is the code review/"
        result = classifier._validated_llm_classification(
            {
                "route": "administrative",
                "question_type": "what",
                "target_concepts": ["unit testing", "code review"],
                "conversation_state": "changing_topic",
                "dialogue_status": "new_topic",
                "conversation_action": "continue",
                "retrieval_query": "what is code review",
                "operational_request": "none",
            },
            message,
            classifier._rule_classification(message, [
                ChatMessage(role="user", content="what is the unit testing"),
            ]),
        )
        self.assertEqual(result.route, "learning")
        self.assertEqual(result.target_concepts, ("code review",))
        self.assertEqual(result.conversation_state, "changing_topic")

    def classify_with_rules(
        self, message: str, history: list[ChatMessage] | None = None,
    ) -> MessageClassification:
        with patch.object(settings, "CLASSIFIER_ENABLED", False):
            return asyncio.run(classify_message(message, history or []))

    def test_extracts_clean_concept_from_explain_what_question(self) -> None:
        result = self.classify_with_rules("Explain what GitHub is.")
        self.assertEqual(result.route, "learning")
        self.assertEqual(result.target_concepts, ("GitHub",))
        self.assertEqual(result.target, "GitHub")

    def test_opening_definition_is_not_mistaken_for_support_request(self) -> None:
        message = "what is the version control"
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "question_type": "what",
                "conversation_state": "new_concept",
                "dialogue_status": "requesting_support",
                "support_level": 1,
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.dialogue_status, "new_topic")
        self.assertEqual(result.conversation_state, "new_concept")

    def test_question_about_previous_tutor_wording_is_not_clarified_again(self) -> None:
        message = 'what is the "his original approach meaning" in the context'
        history = [ChatMessage(role="assistant", content=(
            "Alex explains his payment bug fix to Sam without changing his original approach. "
            "How can he make the logic clear?"
        ))]
        mistaken = MessageClassification(
            route="learning", question_type="what", conversation_state="uncertain",
            dialogue_status="requesting_support", conversation_action="clarify",
            confidence=0.95, needs_clarification=True,
            clarification_question="Could you clarify what you want to explore or verify?",
        )
        with patch("app.classifier._classify_with_llm", return_value=mistaken):
            result = asyncio.run(classify_message(message, history, "What is code review?"))
        self.assertEqual(result.conversation_state, "follow_up")
        self.assertEqual(result.conversation_action, "continue")
        self.assertFalse(result.needs_clarification)
        self.assertIsNone(result.clarification_question)

    def test_administrative_questions_are_protected_by_rules(self) -> None:
        result = self.classify_with_rules("What are the Assignment 4 submission requirements?")
        self.assertEqual(result.route, "administrative")
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
        self.assertEqual(result.question_type, "comparison")
        self.assertEqual(result.target_concepts, ("Git", "GitHub"))

    def test_short_ambiguous_message_requests_clarification(self) -> None:
        result = self.classify_with_rules("configuration")
        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.route, "unclear")
        self.assertIn("course concept", result.clarification_question or "")

    def test_classifier_keeps_all_relevant_concepts_without_a_topic_list(self) -> None:
        message = "How do energy, water, light, carbon, and temperature interact?"
        result = classifier._validated_llm_classification(
            {
                "target_concepts": ["energy", "water", "light", "carbon", "temperature"],
                "retrieval_query": message,
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(
            result.target_concepts,
            ("energy", "water", "light", "carbon", "temperature"),
        )

    def test_compound_question_keeps_distinct_grounded_searches(self) -> None:
        message = "How do code review and automated tests catch different defects?"
        result = classifier._validated_llm_classification(
            {
                "retrieval_query": "code review automated tests defect detection",
                "retrieval_subqueries": [
                    "code review defect detection",
                    "automated tests defect detection",
                    "unrelated astronomy topic",
                ],
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(
            result.retrieval_subqueries,
            ("code review defect detection", "automated tests defect detection"),
        )

    def test_substantive_tutor_answer_is_evaluated_even_when_model_requests_clarification(self) -> None:
        message = "They need to check whether their code is properly organized or not"
        history = [
            ChatMessage(role="user", content="What is version control?"),
            ChatMessage(
                role="assistant",
                content=(
                    "Imagine two developers edit the same file in a shared project. "
                    "What problem should they solve before combining their changes?"
                ),
            ),
        ]
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "question_type": "statement",
                "target_concepts": ["version control"],
                "conversation_state": "answering_tutor",
                "dialogue_status": "answering_tutor",
                "conversation_action": "continue",
                "has_substantive_claim": True,
                "student_claim": message,
                "confidence": 0.6,
                "needs_clarification": True,
                "clarification_question": "Is your answer about detecting conflicts before merging?",
                "retrieval_query": "version control conflict detection code organization",
            },
            message,
            classifier._rule_classification(message, history),
        )

        self.assertFalse(result.needs_clarification)
        self.assertIsNone(result.clarification_question)
        self.assertEqual(result.conversation_action, "continue")
        self.assertTrue(should_evaluate_answer(message, history, result))

    def test_llm_output_is_validated_and_used_for_learning_message(self) -> None:
        payload = """{
            "route": "learning",
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
        self.assertEqual(result.conversation_state, "new_concept")
        self.assertEqual(result.conversation_action, "continue")

    def test_llm_routes_a_substantive_confirmation_request_to_claim_check(self) -> None:
        message = "I think Git and GitHub are the same. Is that correct?"
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
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

    def test_merge_conflict_answer_is_evaluated_even_when_it_says_cannot_be_combined(self) -> None:
        message = (
            "A merge conflict will inevitably occur because both developers changed the same file "
            "independently, so their changes cannot be combined automatically."
        )
        history = [ChatMessage(role="assistant", content="What happens when both teammates edit the same file?")]
        fallback = classifier._rule_classification(message, history)
        result = classifier._validated_llm_classification(
            {
                "route": "learning", "question_type": "what",
                "target_concepts": ["merge conflict"], "conversation_state": "possible_misconception",
                "dialogue_status": "requesting_confirmation", "conversation_action": "verify_claim",
                "has_substantive_claim": True, "student_claim": message, "confidence": 0.95,
                "needs_clarification": False, "retrieval_query": "merge conflict definition",
            },
            message,
            fallback,
        )
        self.assertEqual(result.question_type, "statement")
        self.assertEqual(result.conversation_action, "continue")
        self.assertNotEqual(result.dialogue_status, "requesting_confirmation")
        self.assertTrue(should_evaluate_answer(message, history, result))

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
