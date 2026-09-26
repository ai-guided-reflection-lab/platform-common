import unittest
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import rag
from app.answer_evaluation import AnswerEvaluation
from app.classifier import MessageClassification
from app.schemas import ChatMessage, Source
from app.socratic import choose_socratic_strategy, conversation_scenario, socratic_system_instruction


SCENARIO = "Imagine you and a friend share a document and want to preserve earlier versions. What would you do?"
SOURCE = Source(document_id="doc", chunk_id="chunk", title="Version control", text="Version control preserves revisions.", score=1)
CLASSIFICATION = MessageClassification(conversation_state="answering_tutor", dialogue_status="answering_tutor", target="version control")
EVALUATION = AnswerEvaluation(concept="version control", keyword_coverage=0.7, semantic_alignment=0.8,
    rubric_score=0.8, total_score=80, correctness=3, completeness=3, reasoning=3,
    application=None, supported_concepts=("revision history",), missing_concepts=(),
    critical_misconception=False, misconception=None, feedback="You explained preserved revisions.",
    confidence=0.9, progress_status="developing")


class ScenarioContinuityTests(unittest.TestCase):
    def test_activity_offer_is_replaced_with_reasoning_question(self):
        model_reply = (
            "Imagine Alice creates a private GitHub repository for her project. "
            "Would you like to try creating a similar repository step by step?"
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=model_reply))]
        )
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        with patch(
            "app.rag.generation_client_config",
            return_value=("Ollama", "ollama", "http://localhost:11434/v1", "test-model"),
        ), patch("openai.AsyncOpenAI", return_value=client):
            answer = asyncio.run(
                rag.generate_answer(
                    "I want to keep my code safe.",
                    [],
                    [SOURCE],
                    CLASSIFICATION,
                )
            )

        self.assertNotIn("Would you like", answer)
        self.assertEqual(
            answer,
            "Imagine Alice creates a private GitHub repository for her project. "
            "What detail in this situation shows how version control works, "
            "and why does that detail matter?",
        )
        instruction = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("must require reasoning", instruction)
        self.assertIn("Never end with a consent", instruction)

    def test_contextual_wording_request_keeps_previous_tutor_question_in_prompt(self):
        previous = (
            "Alex explains his payment bug fix to Sam without changing his original approach. "
            "How can he make the logic clear?"
        )
        history = [ChatMessage(role="assistant", content=previous)]
        model_reply = "His original approach means Alex's existing method for fixing the payment bug."
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=model_reply))])
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("app.rag.generation_client_config", return_value=(
            "Groq", "groq-test-key", "https://api.groq.com/openai/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            answer = asyncio.run(rag.generate_answer(
                'what is the "his original approach meaning" in the context', history, [],
            ))
        messages = create.call_args.kwargs["messages"]
        self.assertIn({"role": "assistant", "content": previous}, messages)
        self.assertIn("Resolve references from the conversation", messages[0]["content"])
        self.assertEqual(answer, model_reply)

    def test_generation_receives_old_example_plus_recent_exchange(self):
        history = [ChatMessage(role="assistant", content=SCENARIO)]
        history += [ChatMessage(role="user", content="Save a revision."), ChatMessage(role="assistant", content="Why preserve it?")] * 8
        model_reply = (
            "You identified the value of saving a revision.\n\n"
            "Why would saving that revision help you and your friend with the shared document? "
            "What would you do next?"
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=model_reply)
                )
            ]
        )
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("app.rag.generation_client_config", return_value=("openai", "test-key", "https://api.openai.com/v1", "test-model")), patch("openai.AsyncOpenAI", return_value=client):
            answer = asyncio.run(rag.generate_answer(
                "We can restore earlier work.", history, [SOURCE], CLASSIFICATION, EVALUATION,
                learning_topic="What is version control?",
            ))
        messages = create.call_args.kwargs["messages"]
        self.assertIn("Imagine you and a friend share a document and want to preserve earlier versions.", messages[1]["content"])
        self.assertNotIn("What would you do", messages[1]["content"])
        self.assertNotIn("What would you do?</scenario>", messages[1]["content"])
        self.assertIn("do not repeat or paraphrase", messages[1]["content"])
        self.assertIn("<learning_topic>What is version control?</learning_topic>", messages[1]["content"])
        self.assertIn("primary teaching objective", messages[1]["content"])
        self.assertIn("Do not keep quizzing the student on the detail's inner workings", messages[1]["content"])
        self.assertIn("Earlier tutor-generated examples are conversation context, not course evidence", messages[0]["content"])
        self.assertNotIn("Why preserve it?", str(messages))
        self.assertEqual(sum(item["role"] == "assistant" for item in messages), 0)
        self.assertEqual(answer, model_reply)

    def test_complete_answer_advances_josh_scenario_without_old_question_in_prompt(self):
        prior_question = "How does this allow Josh to recover from a mistake without tracking versions?"
        history = [
            ChatMessage(role="assistant", content=f"Imagine Josh working on a project. {prior_question}"),
            ChatMessage(role="user", content="Josh can restore an earlier project state."),
            ChatMessage(role="assistant", content=prior_question),
        ]
        evaluation = replace(
            EVALUATION, total_score=79.17, correctness=4, completeness=3, reasoning=3,
            missing_concepts=(), progress_status="developing",
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content="What should Josh decide before restoring an older project state?"
        ))])
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("app.rag.generation_client_config", return_value=(
            "Groq", "groq-test-key", "https://api.groq.com/openai/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            asyncio.run(rag.generate_answer(
                "Josh can restore an earlier project state without tracking versions.",
                history, [SOURCE], CLASSIFICATION, evaluation,
            ))
        messages = create.call_args.kwargs["messages"]
        self.assertNotIn(prior_question.rstrip("?"), str(messages))
        self.assertIn("next decision or consequence", messages[1]["content"])
        self.assertNotIn("Convert the most important missing concept", messages[1]["content"])

    def test_original_example_survives_beyond_eight_messages(self):
        history = [ChatMessage(role="assistant", content=SCENARIO)]
        history += [ChatMessage(role="user", content="Save a revision."), ChatMessage(role="assistant", content="Why preserve it?")] * 8
        decision = choose_socratic_strategy("We can restore earlier work.", history, [SOURCE], CLASSIFICATION, EVALUATION)
        self.assertEqual(decision.scenario_anchor, SCENARIO)
        self.assertIn("Imagine you and a friend share a document and want to preserve earlier versions.", socratic_system_instruction(decision))
        self.assertNotIn("What would you do", socratic_system_instruction(decision))
        self.assertNotIn("What would you do?</scenario>", socratic_system_instruction(decision))
        self.assertEqual(decision.strategy, "probe_reasoning")

    def test_difficulty_simplifies_existing_example(self):
        decision = choose_socratic_strategy("I am stuck.", [ChatMessage(role="assistant", content=SCENARIO)], [SOURCE],
            replace(CLASSIFICATION, support_level=2))
        self.assertEqual(decision.example_type, "simplified_current_example")
        self.assertEqual(decision.scenario_anchor, SCENARIO)
        self.assertIn("same people", decision.instruction)

    def test_explicit_uncertainty_overrides_incorrect_new_concept_classification(self):
        misclassified = replace(
            CLASSIFICATION,
            conversation_state="new_concept",
            target="version control",
        )
        decision = choose_socratic_strategy(
            "I don't know why we have to do this in software engineering",
            [ChatMessage(role="assistant", content=SCENARIO)],
            [SOURCE],
            misclassified,
        )

        self.assertEqual(decision.student_state, "uncertain")
        self.assertEqual(decision.strategy, "scaffold_then_question")
        self.assertEqual(decision.scenario_anchor, SCENARIO)


    def test_evidence_drives_moves(self):
        cases = [(replace(EVALUATION, correctness=0), "scaffold_then_question"),
                 (replace(EVALUATION, critical_misconception=True), "guided_comparison"),
                 (replace(EVALUATION, missing_concepts=("restoration",)), "extend_scenario"),
                 (EVALUATION, "probe_reasoning"),
                 (replace(EVALUATION, progress_status="ready_for_verification"), "mastery_verification")]
        for evaluation, expected in cases:
            with self.subTest(expected=expected):
                decision = choose_socratic_strategy("My answer", [], [SOURCE], CLASSIFICATION, evaluation)
                self.assertEqual(decision.strategy, expected)

    def test_evaluation_overrides_a_provisional_misconception_label(self):
        classified = replace(CLASSIFICATION, conversation_state="possible_misconception")
        decision = choose_socratic_strategy(
            "A merge conflict can happen when changes cannot be combined automatically.",
            [ChatMessage(role="assistant", content="What happens when both teammates edit the same file?")],
            [SOURCE], classified, EVALUATION,
        )
        self.assertEqual(decision.strategy, "probe_reasoning")






    def test_plain_good_answer_cannot_be_forced_into_grounded_claim_explanation(self):
        software_scenario = (
            "Imagine two developers edit the same file in a shared project, and neither wants to overwrite the "
            "other's work. What problem should they solve before combining their changes?"
        )
        misclassified = replace(
            CLASSIFICATION,
            conversation_action="verify_claim",
            has_substantive_claim=True,
            student_claim="Version control reduces code conflicts.",
            target="version control",
        )
        decision = choose_socratic_strategy(
            "It reduces code conflicts in a team.",
            [ChatMessage(role="assistant", content=software_scenario)],
            [SOURCE],
            misclassified,
            replace(EVALUATION, correctness=3, missing_concepts=()),
        )
        self.assertEqual(decision.strategy, "probe_reasoning")



    def test_explicit_example_change_resets_anchor(self):
        history = [ChatMessage(role="assistant", content=SCENARIO)]
        decision = choose_socratic_strategy("Use a different example.", history, [SOURCE], CLASSIFICATION)
        self.assertIsNone(decision.scenario_anchor)
        history += [ChatMessage(role="user", content="Use a different example."),
                    ChatMessage(role="assistant", content="Suppose your team tests a login feature. Where would you work?")]
        self.assertIn("login feature", conversation_scenario(history))

    def test_topic_change_classification_does_not_reset_scenario(self):
        classification = replace(
            CLASSIFICATION, conversation_state="changing_topic",
            target_concepts=("code review",), target="code review",
        )
        decision = choose_socratic_strategy(
            "what is the code review/",
            [ChatMessage(role="assistant", content=SCENARIO)],
            [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "diagnostic_recall")
        self.assertEqual(decision.scenario_anchor, SCENARIO)

    def test_transfer_keeps_original_example_available(self):
        decision = choose_socratic_strategy("I can explain it.", [ChatMessage(role="assistant", content=SCENARIO)], [SOURCE], CLASSIFICATION,
            replace(EVALUATION, progress_status="ready_for_verification"))
        self.assertEqual(decision.scenario_anchor, SCENARIO)
        self.assertIn("change only one condition", decision.instruction)
