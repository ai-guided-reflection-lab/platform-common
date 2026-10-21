from __future__ import annotations

import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import classifier, settings
from app.answer_evaluation import should_evaluate_answer
from app.classifier import MessageClassification, classify_message
from app.schemas import ChatMessage, ClarificationOption


class MessageClassifierTests(unittest.TestCase):
    def test_unknown_recent_term_is_a_follow_up_and_corrects_transposed_acronym(self) -> None:
        message = "I don't know what the PATL is"
        history = [
            ChatMessage(role="assistant", content="Ask the reviewer to PTAL after you upload the revision."),
            ChatMessage(role="assistant", content="Would you use PATL here?"),
        ]
        mistaken = MessageClassification(
            message_role="support_request",
            route="learning",
            target_concepts=("PATL",),
            dialogue_status="requesting_support",
            conversation_action="continue",
            rewritten_query="definition of PATL in code review",
            source="llm",
        )

        with patch("app.classifier._classify_with_llm", return_value=mistaken):
            result = asyncio.run(classify_message(message, history, "What is code review?"))

        self.assertEqual(result.message_role, "follow_up")
        self.assertEqual(classifier.recent_term_correction(message, history), ("PATL", "PTAL"))

    def test_new_concept_question_cannot_become_administrative(self) -> None:
        message = "what is the code review/"
        result = classifier._validated_llm_classification(
            {
                "route": "administrative",
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
        self.assertEqual(result.message_role, "topic_change")

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
                "conversation_state": "new_concept",
                "dialogue_status": "requesting_support",
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.dialogue_status, "new_topic")
        self.assertEqual(result.message_role, "learning_question")

    def test_recognized_truth_table_question_is_not_replaced_by_clarification(self) -> None:
        message = "p q p ⇔ q\nF F T\nF T F\nT F F\nT T T\n\nwhat is that?"
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "target_concepts": ["truth table", "logical equivalence", "biconditional operator"],
                "conversation_state": "uncertain",
                "dialogue_status": "requesting_support",
                "conversation_action": "clarify",
                "confidence": 0.95,
                "needs_clarification": False,
                "clarification_question": None,
                "retrieval_query": "truth table for p q p iff q",
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.target, "truth table")
        self.assertEqual(result.conversation_action, "continue")
        self.assertFalse(result.needs_clarification)
        self.assertIsNone(result.clarification_question)

    def test_explicitly_ambiguous_question_still_requests_clarification(self) -> None:
        message = "Can you explain it?"
        result = classifier._validated_llm_classification(
            {
                "route": "unclear",
                "conversation_action": "clarify",
                "confidence": 0.5,
                "needs_clarification": True,
                "clarification_question": "Which course concept do you mean?",
            },
            message,
            classifier._rule_classification(message, []),
        )
        self.assertEqual(result.conversation_action, "clarify")
        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.clarification_question, "Which course concept do you mean?")

    def test_question_about_previous_tutor_wording_is_not_clarified_again(self) -> None:
        message = 'what is the "his original approach meaning" in the context'
        history = [ChatMessage(role="assistant", content=(
            "Alex explains his payment bug fix to Sam without changing his original approach. "
            "How can he make the logic clear?"
        ))]
        mistaken = MessageClassification(
            route="learning",
            dialogue_status="requesting_support", conversation_action="clarify",
            confidence=0.95, needs_clarification=True,
            clarification_question="Could you clarify what you want to explore or verify?",
        )
        with patch("app.classifier._classify_with_llm", return_value=mistaken):
            result = asyncio.run(classify_message(message, history, "What is code review?"))
        self.assertEqual(result.message_role, "follow_up")
        self.assertEqual(result.conversation_action, "continue")
        self.assertFalse(result.needs_clarification)
        self.assertIsNone(result.clarification_question)

    def test_request_to_make_previous_question_clearer_is_not_clarified_again(self) -> None:
        message = "Sorry, I didn't get your question. Can you make it a bit clearer?"
        history = [ChatMessage(
            role="assistant",
            content=(
                "If they say the loop is needed for a specific reason, what is one simple way "
                "you could ask them to clarify that reason without changing your logic?"
            ),
        )]
        mistaken = MessageClassification(
            route="unclear",
            dialogue_status="requesting_support", conversation_action="clarify",
            confidence=0.95, needs_clarification=True,
            clarification_question="Could you clarify what you want to explore or verify?",
            source="llm",
        )
        with patch("app.classifier._classify_with_llm", return_value=mistaken):
            result = asyncio.run(classify_message(message, history, "Explain code review to me"))
        self.assertEqual(result.route, "learning")
        self.assertEqual(result.message_role, "support_request")
        self.assertEqual(result.message_role, "support_request")
        self.assertEqual(result.conversation_action, "continue")
        self.assertFalse(result.needs_clarification)

    def test_declarative_answer_to_tutor_is_not_treated_as_clarification_request(self) -> None:
        message = "it's very hard to identify which part improves and changes."
        history = [
            ChatMessage(role="user", content="What is code review?"),
            ChatMessage(role="assistant", content=(
                "If Alex submits a massive change instead of keeping it small, "
                "what happens to the team's review?"
            )),
        ]
        mistaken = MessageClassification(
            route="learning",
            target_concepts=("identifying improvements", "massive changes"), dialogue_status="requesting_support",
            conversation_action="clarify", confidence=0.85, needs_clarification=True,
            clarification_question="Could you clarify what you want to explore or verify?",
            source="llm",
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"relationship":"answer","substantive_answer":true}'
        ))])
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.chat.completions.create.return_value = response
        with patch("app.classifier._classify_with_llm", return_value=mistaken), patch(
            "app.classifier._client_config", return_value=("Ollama", "ollama", "http://localhost:11434/v1", "qwen")
        ), patch("openai.AsyncOpenAI", return_value=client):
            result = asyncio.run(classify_message(message, history, "What is code review?"))
        self.assertEqual(result.dialogue_status, "answering_tutor")
        self.assertEqual(result.conversation_action, "continue")
        self.assertTrue(result.has_substantive_claim)
        self.assertFalse(result.needs_clarification)
        self.assertTrue(should_evaluate_answer(message, history, result))

    def test_explicit_uncertainty_still_gets_support(self) -> None:
        message = "I'm confused and don't know what changes."
        history = [ChatMessage(role="assistant", content="What happens when the change gets large?")]
        support = MessageClassification(
            route="learning",
            dialogue_status="requesting_support", conversation_action="clarify",
            needs_clarification=True, clarification_question="Which part is confusing?",
            source="llm",
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"relationship":"support_request","substantive_answer":false}'
        ))])
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.chat.completions.create.return_value = response
        with patch("app.classifier._classify_with_llm", return_value=support), patch(
            "app.classifier._client_config", return_value=("Ollama", "ollama", "http://localhost:11434/v1", "qwen")
        ), patch("openai.AsyncOpenAI", return_value=client):
            result = asyncio.run(classify_message(message, history, "What is code review?"))
        self.assertFalse(result.needs_clarification)
        self.assertEqual(result.conversation_action, "continue")
        self.assertEqual(result.dialogue_status, "requesting_support")
        self.assertFalse(should_evaluate_answer(message, history, result))

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

    def test_natural_comparison_question_finds_both_concepts_without_a_question_type(self) -> None:
        result = self.classify_with_rules("How are Git and GitHub different?")
        self.assertEqual(result.target_concepts, ("Git", "GitHub"))
        self.assertNotIn("question_type", classifier.CLASSIFICATION_SCHEMA["properties"])

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
                "target_concepts": ["version control"],
                "conversation_state": "answering_tutor",
                "dialogue_status": "answering_tutor",
                "conversation_action": "continue",
                "has_substantive_claim": True,
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
                "target_concepts": ["version control"],
                "conversation_state": "claiming_understanding",
                "dialogue_status": "claiming_understanding",
                "conversation_action": "verify_understanding",
                "has_substantive_claim": False,
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
        self.assertEqual(result.message_role, "learning_question")
        self.assertEqual(result.conversation_action, "continue")

    def test_llm_routes_a_substantive_confirmation_request_to_claim_check(self) -> None:
        message = "I think Git and GitHub are the same. Is that correct?"
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "target_concepts": ["Git", "GitHub"],
                "conversation_state": "possible_misconception",
                "dialogue_status": "requesting_confirmation",
                "conversation_action": "verify_claim",
                "has_substantive_claim": True,
                "wants_to_continue": True,
                "confidence": 0.97,
                "needs_clarification": False,
                "retrieval_query": "Git and GitHub relationship",
            },
            message,
            classifier._rule_classification(message, []),
        )
        # Python derives one consistent policy: grounded confirmation is an
        # evaluable answer that continues through retrieval and evaluation.
        self.assertEqual(result.message_role, "confirmation_request")
        self.assertEqual(result.conversation_action, "continue")
        self.assertTrue(result.has_substantive_claim)

    def test_llm_cannot_treat_plain_student_answer_as_confirmation_request(self) -> None:
        message = "It reduces code conflicts in a team."
        fallback = classifier._rule_classification(
            message,
            [ChatMessage(role="assistant", content="What problem might version control help solve?")],
        )
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "target_concepts": ["version control"],
                "conversation_state": "possible_misconception",
                "dialogue_status": "requesting_confirmation",
                "conversation_action": "verify_claim",
                "has_substantive_claim": True,
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
                "route": "learning",
                "target_concepts": ["merge conflict"], "conversation_state": "possible_misconception",
                "dialogue_status": "requesting_confirmation", "conversation_action": "verify_claim",
                "has_substantive_claim": True, "confidence": 0.95,
                "needs_clarification": False, "retrieval_query": "merge conflict definition",
            },
            message,
            fallback,
        )
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
        self.assertEqual(result.message_role, "closing")
        self.assertEqual(result.conversation_action, "complete")
        self.assertFalse(result.wants_to_continue)

    def test_llm_can_explicitly_classify_document_listing_request(self) -> None:
        message = "Which documents are currently published for this course?"
        result = classifier._validated_llm_classification(
            {
                "route": "administrative",
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

    def test_llm_classifies_support_without_assigning_a_hint_level(self) -> None:
        message = "I still do not understand code review."
        result = classifier._validated_llm_classification(
            {
                "route": "learning",
                "target_concepts": ["code review"],
                "conversation_state": "uncertain",
                "dialogue_status": "uncertain",
                "conversation_action": "continue",
                "understanding_level": "beginner",
                "confidence": 0.96,
                "needs_clarification": False,
                "retrieval_query": "code review purpose process",
            },
            message,
            classifier._rule_classification(message, []),
        )
        # The pre-retrieval classifier no longer claims to measure mastery.
        self.assertEqual(result.understanding_level, "unknown")
        self.assertEqual(result.message_role, "support_request")

    def test_live_schema_contains_observations_not_controller_commands(self) -> None:
        properties = classifier.CLASSIFICATION_SCHEMA["properties"]
        self.assertIn("message_role", properties)
        self.assertNotIn("student_claim", properties)
        self.assertNotIn("support_level", properties)
        self.assertIn("retrieval_query", properties)
        self.assertIn("clarification_question", properties)
        self.assertIn("clarification_options", properties)
        for controller_field in (
            "route", "conversation_state", "dialogue_status", "conversation_action",
            "needs_clarification", "understanding_level",
        ):
            self.assertNotIn(controller_field, properties)

    def test_single_message_role_derives_consistent_controller_policy(self) -> None:
        result = classifier._validated_llm_classification(
            {
                "message_role": "support_request",
                "target_concepts": ["code review"],
                "missing_context": None,
                "retrieval_query": "code review previous tutor question",
                "retrieval_subqueries": [],
                "operational_request": "none",
            },
            "Could you explain that question more simply?",
            classifier._rule_classification("Could you explain that question more simply?", []),
        )
        self.assertEqual(result.message_role, "support_request")
        self.assertEqual(result.dialogue_status, "requesting_support")
        self.assertEqual(result.conversation_action, "continue")
        self.assertFalse(result.needs_clarification)
        self.assertFalse(result.assessment_candidate)

        answer = classifier._classification_from_observation(
            message_role="student_answer",
            concepts=("code review",),
        )
        self.assertTrue(answer.assessment_candidate)

    def test_mixed_uncertainty_and_tentative_answer_can_request_clickable_clarification(self) -> None:
        message = "I'm not sure. Perhaps, any updates from me?"
        history = [
            ChatMessage(role="assistant", content="What specific change would you add to the repository?"),
        ]
        ambiguous = classifier._classification_from_observation(
            message_role="ambiguous",
            concepts=("repository",),
            missing_context="whether the student is answering or asking for another example",
            clarification_question="Which meaning did you intend?",
            clarification_options=(
                ClarificationOption(
                    label="Any update could be reviewed",
                    message_role="student_answer",
                    resolved_message="I am suggesting that any update I make could be reviewed.",
                ),
                ClarificationOption(
                    label="Give me another example",
                    message_role="support_request",
                    resolved_message="I would like another example of a repository update.",
                ),
            ),
        )
        with patch("app.classifier._classify_with_llm", new_callable=AsyncMock, return_value=ambiguous):
            result = asyncio.run(classify_message(message, history, learning_topic="What is code review?"))

        self.assertEqual(result.message_role, "ambiguous")
        self.assertTrue(result.needs_clarification)
        self.assertEqual([option.message_role for option in result.clarification_options], [
            "student_answer", "support_request",
        ])
        self.assertFalse(result.assessment_candidate)

    def test_plain_uncertainty_remains_a_support_request(self) -> None:
        message = "I'm not sure."
        history = [ChatMessage(role="assistant", content="Why should Sam review the change?")]
        ambiguous = classifier._classification_from_observation(
            message_role="ambiguous",
            clarification_question="What did you mean?",
            clarification_options=(
                ClarificationOption(
                    label="I am answering",
                    message_role="student_answer",
                    resolved_message="I am answering the question.",
                ),
                ClarificationOption(
                    label="I need help",
                    message_role="support_request",
                    resolved_message="I need help with the question.",
                ),
            ),
        )
        with patch("app.classifier._classify_with_llm", new_callable=AsyncMock, return_value=ambiguous):
            result = asyncio.run(classify_message(message, history, learning_topic="What is code review?"))

        self.assertEqual(result.message_role, "support_request")
        self.assertFalse(result.needs_clarification)
        self.assertEqual(result.clarification_options, ())


if __name__ == "__main__":
    unittest.main()


def test_scoped_classifier_preserves_scope_verdict_through_role_normalization():
    result = MessageClassification(message_role="learning_question", keyword_scope_match=False, source="llm")
    with patch("app.classifier._classify_with_llm", new_callable=AsyncMock, return_value=result):
        actual = asyncio.run(classify_message("Just tell me about a different subject", [], allowed_keywords=("code review",)))
    assert actual.message_role == "direct_answer_request"
    assert actual.keyword_scope_match is False


def test_scoped_classifier_sends_keyword_boundary_and_keeps_global_schema_unchanged():
    import json
    payload={"message_role":"learning_question","target_concepts":["SQL joins"],"missing_context":None,
        "clarification_question":None,"clarification_options":[],"retrieval_query":"SQL joins",
        "retrieval_subqueries":[],"operational_request":"none","keyword_scope_match":False}
    response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    completion=AsyncMock(return_value=response)
    with patch("app.classifier._client_config",return_value=("Groq","test","http://test.invalid","model")), patch("app.classifier.chat_completion",completion):
        result=asyncio.run(classify_message("Explain SQL joins",[],allowed_keywords=("code review",)))
    request=completion.call_args.args[2]
    assert result.keyword_scope_match is False
    assert 'code review' in request['messages'][0]['content']
    assert 'keyword_scope_match' in request['response_format']['json_schema']['schema']['required']
    assert 'keyword_scope_match' not in classifier.CLASSIFICATION_SCHEMA['properties']
