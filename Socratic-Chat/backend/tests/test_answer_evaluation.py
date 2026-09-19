from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.answer_evaluation import (
    answer_evaluation_query,
    concept_coverage,
    evaluate_student_answer,
    evaluation_tutor_instruction,
    should_evaluate_answer,
    validated_evaluation,
    with_progress_status,
)
from app.classifier import MessageClassification
from app import db
from app.schemas import ChatMessage, Source


def answering_classification() -> MessageClassification:
    return MessageClassification(
        student_intent="reflection",
        question_type="follow_up",
        target_concepts=("version control",),
        conversation_state="answering_tutor",
        dialogue_status="answering_tutor",
        conversation_action="continue",
        has_substantive_claim=True,
        target="version control",
        rewritten_query="version control tracks changes",
        confidence=0.95,
        source="llm",
    )


class AnswerEvaluationTests(unittest.TestCase):
    def test_openai_gpt_4_1_mini_uses_strict_schema(self) -> None:
        payload = {
            "concept": "version control",
            "expected_concepts": [
                {"name": "revision history", "accepted_terms": ["tracks changes"]},
            ],
            "semantic_alignment": 0.9,
            "correctness": 4,
            "completeness": 3,
            "reasoning": 3,
            "application": 1,
            "understanding_improved": None,
            "supported_concepts": ["revision history"],
            "missing_concepts": [],
            "critical_misconception": False,
            "misconception": None,
            "feedback": "You identified revision history.",
            "confidence": 0.9,
        }
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        )
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        history = [ChatMessage(role="assistant", content="Why does version control help teams?")]
        source = Source(
            document_id="doc-1", chunk_id="chunk-1", title="course.html",
            text="Version control tracks revisions.", score=0.9,
        )
        with (
            patch("openai.AsyncOpenAI", return_value=client),
            patch("app.answer_evaluation.settings.OPENAI_API_KEY", "test-key"),
            patch("app.answer_evaluation.settings.RAG_MODEL", "gpt-4.1-mini"),
        ):
            evaluation = asyncio.run(
                evaluate_student_answer(
                    "It tracks changes over time.", history, [source],
                    answering_classification(), concept_hint="version control",
                )
            )
        self.assertIsNotNone(evaluation)
        request = create.await_args.kwargs
        self.assertEqual(request["response_format"]["type"], "json_schema")
        self.assertTrue(request["response_format"]["json_schema"]["strict"])
        self.assertEqual(request["model"], "gpt-4.1-mini")
        self.assertNotIn("extra_body", request)

    def test_mastery_requires_repeated_evidence_then_transfer_verification(self) -> None:
        first = db._mastery_progress_update(None, 85, 4, 2, False)
        second = db._mastery_progress_update(first, 88, 4, 2, False)
        final = db._mastery_progress_update(second, 90, 4, 3, False)
        self.assertEqual(first[2], "developing")
        self.assertEqual(second[2], "ready_for_verification")
        self.assertEqual(final[2], "mastered")

    def test_critical_misconception_routes_to_support(self) -> None:
        progress = db._mastery_progress_update((90, 2, "ready_for_verification"), 59, 1, 0, True)
        self.assertEqual(progress[2], "needs_support")

    def test_substantive_reply_to_tutor_question_is_eligible(self) -> None:
        history = [ChatMessage(role="assistant", content="Why might a team use version control?")]
        self.assertTrue(
            should_evaluate_answer(
                "Because it preserves changes made by different developers.",
                history,
                answering_classification(),
            )
        )

    def test_new_question_or_understanding_claim_is_not_scored(self) -> None:
        history = [ChatMessage(role="assistant", content="Why might a team use version control?")]
        new_topic = MessageClassification(dialogue_status="new_topic")
        understanding = MessageClassification(
            dialogue_status="claiming_understanding",
            conversation_action="verify_understanding",
        )
        self.assertFalse(should_evaluate_answer("What is code review?", history, new_topic))
        self.assertFalse(should_evaluate_answer("I understand it now.", history, understanding))

    def test_evaluation_query_includes_tutor_question_for_elliptical_answer(self) -> None:
        history = [ChatMessage(role="assistant", content="Why might a team use version control?")]
        query = answer_evaluation_query(
            "Because it tracks changes.", history, answering_classification(),
        )
        self.assertIn("Why might a team use version control?", query)
        self.assertIn("Because it tracks changes.", query)

    def test_keyword_coverage_accepts_aliases(self) -> None:
        expected = (
            ("revision history", ("change history", "tracked revisions")),
            ("collaboration", ("teamwork", "multiple developers")),
        )
        self.assertEqual(
            concept_coverage("It keeps change history for multiple developers.", expected),
            1.0,
        )

    def test_weighted_score_combines_keyword_semantic_and_rubric(self) -> None:
        evaluation = validated_evaluation(
            {
                "concept": "version control",
                "expected_concepts": [
                    {"name": "revision history", "accepted_terms": ["tracks changes"]},
                    {"name": "collaboration", "accepted_terms": ["multiple developers"]},
                ],
                "semantic_alignment": 0.8,
                "correctness": 4,
                "completeness": 3,
                "reasoning": 3,
                "application": 2,
                "understanding_improved": True,
                "supported_concepts": ["revision history"],
                "missing_concepts": ["collaboration"],
                "critical_misconception": False,
                "misconception": None,
                "feedback": "You correctly identified revision history.",
                "confidence": 0.9,
            },
            "It tracks changes.",
            "version control",
        )
        self.assertEqual(evaluation.keyword_coverage, 0.5)
        self.assertEqual(evaluation.rubric_score, 0.8)
        self.assertEqual(evaluation.total_score, 74.0)

    def test_unassessed_application_is_not_treated_as_zero(self) -> None:
        evaluation = validated_evaluation(
            {
                "concept": "version control",
                "expected_concepts": [
                    {"name": "revision history", "accepted_terms": ["tracks changes"]},
                ],
                "semantic_alignment": 1,
                "correctness": 4,
                "completeness": 3,
                "reasoning": 3,
                "application": None,
                "understanding_improved": True,
                "supported_concepts": ["revision history"],
                "missing_concepts": [],
                "critical_misconception": False,
                "misconception": None,
                "feedback": "You explained how revision history helps.",
                "confidence": 0.9,
            },
            "It tracks changes over time.",
            "version control",
        )
        self.assertIsNone(evaluation.application)
        self.assertEqual(evaluation.rubric_score, 0.875)
        self.assertEqual(evaluation.total_score, 92.5)

    def test_incomplete_model_payload_is_rejected_instead_of_saved_as_zero(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            validated_evaluation({}, "It tracks changes.", "version control")

    def test_persisted_concept_hint_overrides_a_drifting_model_label(self) -> None:
        evaluation = validated_evaluation(
            {
                "concept": "current concept",
                "expected_concepts": [
                    {"name": "revision history", "accepted_terms": ["tracks changes"]},
                ],
                "semantic_alignment": 0.8,
                "correctness": 3,
                "completeness": 2,
                "reasoning": 2,
                "application": 1,
                "understanding_improved": None,
                "supported_concepts": ["revision history"],
                "missing_concepts": [],
                "critical_misconception": False,
                "misconception": None,
                "feedback": "You identified revision history.",
                "confidence": 0.9,
            },
            "It tracks changes.",
            "version control",
        )
        self.assertEqual(evaluation.concept, "version control")

    def test_critical_misconception_prevents_mastery(self) -> None:
        evaluation = validated_evaluation(
            {
                "concept": "version control",
                "expected_concepts": [{"name": "history", "accepted_terms": ["history"]}],
                "semantic_alignment": 1,
                "correctness": 4,
                "completeness": 4,
                "reasoning": 4,
                "application": 4,
                "understanding_improved": True,
                "supported_concepts": ["history"],
                "missing_concepts": [],
                "critical_misconception": True,
                "misconception": "The answer reverses the role of history.",
                "feedback": "Reconsider how history is preserved.",
                "confidence": 1,
            },
            "history",
            "version control",
        )
        self.assertEqual(evaluation.total_score, 59.0)
        self.assertFalse(evaluation.ready_for_verification)

    def test_recorded_high_score_waits_for_persistent_ready_status(self) -> None:
        evaluation = validated_evaluation(
            {
                "concept": "version control",
                "expected_concepts": [{"name": "history", "accepted_terms": ["history"]}],
                "semantic_alignment": 1,
                "correctness": 4,
                "completeness": 4,
                "reasoning": 4,
                "application": 4,
                "understanding_improved": True,
                "supported_concepts": ["history"],
                "missing_concepts": [],
                "critical_misconception": False,
                "misconception": None,
                "feedback": "You explained the concept correctly.",
                "confidence": 1,
            },
            "history",
            "version control",
        )
        developing = with_progress_status(evaluation, "developing")
        ready = with_progress_status(evaluation, "ready_for_verification")
        self.assertNotIn("final verification task", evaluation_tutor_instruction(developing))
        self.assertIn("final verification task", evaluation_tutor_instruction(ready))


if __name__ == "__main__":
    unittest.main()
