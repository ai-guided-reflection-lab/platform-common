import unittest
import asyncio
import json
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
CLASSIFICATION = MessageClassification( dialogue_status="answering_tutor", target="version control")
EVALUATION = AnswerEvaluation(concept="version control", keyword_coverage=0.7, semantic_alignment=0.8,
    rubric_score=0.8, total_score=80, correctness=3, completeness=3, reasoning=3,
    application=None, supported_concepts=("revision history",), missing_concepts=(),
    critical_misconception=False, misconception=None, feedback="You explained preserved revisions.",
    confidence=0.9, progress_status="developing")


class ScenarioContinuityTests(unittest.TestCase):
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
            "Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            answer = asyncio.run(rag.generate_answer(
                'what is the "his original approach meaning" in the context', history, [],
            ))
        messages = create.call_args.kwargs["messages"]
        self.assertIn({"role": "assistant", "content": previous}, messages)
        self.assertIn("Resolve references from the conversation", messages[0]["content"])
        self.assertIn("documented spelling", messages[0]["content"])
        self.assertIn("Do not redirect a terminology question", messages[0]["content"])
        self.assertEqual(answer, model_reply)

    def test_verified_term_resolution_is_included_in_generation_prompt(self):
        history = [
            ChatMessage(role="assistant", content="Ask the reviewer to PTAL after the update."),
            ChatMessage(role="assistant", content="Would you use PATL here?"),
        ]
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content="I think you mean PTAL: please take another look."
        ))])
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("app.rag.generation_client_config", return_value=(
            "Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            answer = asyncio.run(rag.generate_answer(
                "I don't know what the PATL is", history, [SOURCE],
                term_resolution=("PATL", "PTAL"),
            ))
        messages = create.call_args.kwargs["messages"]
        self.assertIn("learner wrote 'PATL'", messages[1]["content"])
        self.assertIn("published material uses 'PTAL'", messages[1]["content"])
        self.assertEqual(answer, "I think you mean PTAL: please take another look.")

    def test_generation_receives_old_example_plus_recent_exchange(self):
        history = [ChatMessage(role="assistant", content=SCENARIO)]
        history += [ChatMessage(role="user", content="Save a revision."), ChatMessage(role="assistant", content="Why preserve it?")] * 8
        model_reply = "You identified the value of saving a revision.\n\nWhy would saving that revision help you and your friend with the shared document?"
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps({
                        "lead_in": "You identified the value of saving a revision.",
                        "next_question": "Why would saving that revision help you and your friend with the shared document?",
                    }))
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
        self.assertEqual(create.call_args.kwargs["response_format"]["json_schema"]["name"], "socratic_turn")
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
            content=json.dumps({"lead_in": "", "next_question": "What should Josh decide before restoring an older project state?"})
        ))])
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("app.rag.generation_client_config", return_value=(
            "Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            asyncio.run(rag.generate_answer(
                "Josh can restore an earlier project state without tracking versions.",
                history, [SOURCE], CLASSIFICATION, evaluation,
            ))
        messages = create.call_args.kwargs["messages"]
        self.assertNotIn(prior_question.rstrip("?"), str(messages))
        self.assertIn("next grounded decision", messages[1]["content"])
        self.assertNotIn("Convert the most important missing concept", messages[1]["content"])

    def test_repeated_difficulty_requires_model_generated_follow_up_field(self):
        history = [ChatMessage(
            role="assistant",
            content="Imagine Alex submits a payment fix to Sam for review. What should Sam check?",
        )]
        evaluation = replace(EVALUATION, total_score=40.5, understanding_improved=False)
        model_reply = json.dumps({
            "lead_in": "Sam can read Alex's change and check whether it follows the team's style.",
            "next_question": "What should Sam check next to decide whether the payment fix is safe?",
        })
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=model_reply))])
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("app.rag.generation_client_config", return_value=(
            "Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            answer = asyncio.run(rag.generate_answer(
                "Code review keeps the team's style consistent.", history, [SOURCE], CLASSIFICATION,
                evaluation, learning_topic="What is code review?", stable_concept="code review",
            ))
        request = create.call_args.kwargs
        self.assertIn("Strategy: feedback_then_question", request["messages"][1]["content"])
        self.assertIn("Target concept: code review", request["messages"][1]["content"])
        self.assertEqual(request["response_format"]["json_schema"]["schema"]["required"], [
            "lead_in", "next_question",
        ])
        self.assertTrue(answer.endswith("What should Sam check next to decide whether the payment fix is safe?"))

    def test_support_request_keeps_only_latest_unresolved_tutor_question(self):
        old_question = "Why does code consistency matter later?"
        unresolved_question = "What is the primary goal of reviewing Alex's patch?"
        history = [
            ChatMessage(role="assistant", content=old_question),
            ChatMessage(role="user", content="It helps other engineers read the code."),
            ChatMessage(role="assistant", content=unresolved_question),
        ]
        classification = replace(
            CLASSIFICATION,
            message_role="support_request",
            dialogue_status="requesting_support",
            has_substantive_claim=False,
        )
        model_reply = json.dumps({
            "lead_in": "A reviewer checks whether Alex's patch is healthy for the codebase.",
            "next_question": "Should the reviewer focus on protecting code health or preparing a presentation?",
        })
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=model_reply))])
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        with patch("app.rag.generation_client_config", return_value=(
            "Ollama", "ollama", "http://127.0.0.1:11434/v1", "test-model"
        )), patch("openai.AsyncOpenAI", return_value=client):
            asyncio.run(rag.generate_answer(
                "I'm not sure.", history, [SOURCE], classification,
                learning_topic="What is code review?", stable_concept="code review",
            ))

        messages = create.call_args.kwargs["messages"]
        self.assertIn({"role": "assistant", "content": unresolved_question}, messages)
        self.assertNotIn(old_question, str(messages))
        self.assertIn("exact support request", messages[1]["content"])
        self.assertIn("relevance concern", messages[1]["content"])
        self.assertIn("do not automatically retry", messages[1]["content"])

    def test_original_example_survives_beyond_eight_messages(self):
        history = [ChatMessage(role="assistant", content=SCENARIO)]
        history += [ChatMessage(role="user", content="Save a revision."), ChatMessage(role="assistant", content="Why preserve it?")] * 8
        decision = choose_socratic_strategy("We can restore earlier work.", history, [SOURCE], CLASSIFICATION, EVALUATION)
        self.assertEqual(decision.scenario_anchor, SCENARIO)
        self.assertIn("Imagine you and a friend share a document and want to preserve earlier versions.", socratic_system_instruction(decision))
        self.assertNotIn("What would you do", socratic_system_instruction(decision))
        self.assertNotIn("What would you do?</scenario>", socratic_system_instruction(decision))
        self.assertEqual(decision.strategy, "feedback_then_question")

    def test_difficulty_simplifies_existing_example(self):
        decision = choose_socratic_strategy(
            "I am stuck.", [ChatMessage(role="assistant", content=SCENARIO)], [SOURCE],
            replace(CLASSIFICATION, message_role="support_request", dialogue_status="requesting_support"),
        )
        self.assertEqual(decision.example_type, "simplified_current_example")
        self.assertEqual(decision.scenario_anchor, SCENARIO)
        self.assertIn("same people", decision.instruction)

    def test_explicit_uncertainty_overrides_incorrect_new_concept_classification(self):
        misclassified = replace(
            CLASSIFICATION,
            target="version control",
        )
        decision = choose_socratic_strategy(
            "I don't know why we have to do this in software engineering",
            [ChatMessage(role="assistant", content=SCENARIO)],
            [SOURCE],
            misclassified,
        )

        self.assertEqual(decision.student_state, "support_requested")
        self.assertEqual(decision.strategy, "respond_to_support")
        self.assertEqual(decision.scenario_anchor, SCENARIO)


    def test_evidence_drives_moves(self):
        cases = [(replace(EVALUATION, correctness=0), "feedback_then_question"),
                 (replace(EVALUATION, critical_misconception=True), "guided_comparison"),
                 (replace(EVALUATION, missing_concepts=("restoration",)), "feedback_then_question"),
                 (EVALUATION, "feedback_then_question")]
        for evaluation, expected in cases:
            with self.subTest(expected=expected):
                decision = choose_socratic_strategy("My answer", [], [SOURCE], CLASSIFICATION, evaluation)
                self.assertEqual(decision.strategy, expected)

    def test_critical_misconception_targets_first_missing_concept(self):
        evaluation = replace(
            EVALUATION,
            correctness=1,
            critical_misconception=True,
            missing_concepts=("creating a snapshot", "mailing the change to reviewers"),
            feedback="Create a patch and description, then mail it to reviewers.",
            progress_status="mastered",
        )

        decision = choose_socratic_strategy(
            "I could schedule a meeting and practice a presentation.",
            [ChatMessage(role="assistant", content=SCENARIO)],
            [SOURCE], CLASSIFICATION, evaluation,
        )

        self.assertEqual(decision.strategy, "guided_comparison")
        self.assertIn("creating a snapshot", decision.instruction)
        self.assertIn("Do not ask about another dimension", decision.instruction)

    def test_evaluation_overrides_a_provisional_misconception_label(self):
        classified = replace(CLASSIFICATION)
        decision = choose_socratic_strategy(
            "A merge conflict can happen when changes cannot be combined automatically.",
            [ChatMessage(role="assistant", content="What happens when both teammates edit the same file?")],
            [SOURCE], classified, EVALUATION,
        )
        self.assertEqual(decision.strategy, "feedback_then_question")






    def test_plain_good_answer_cannot_be_forced_into_grounded_claim_explanation(self):
        software_scenario = (
            "Imagine two developers edit the same file in a shared project, and neither wants to overwrite the "
            "other's work. What problem should they solve before combining their changes?"
        )
        misclassified = replace(
            CLASSIFICATION,
            conversation_action="verify_claim",
            has_substantive_claim=True,
            target="version control",
        )
        decision = choose_socratic_strategy(
            "It reduces code conflicts in a team.",
            [ChatMessage(role="assistant", content=software_scenario)],
            [SOURCE],
            misclassified,
            replace(EVALUATION, correctness=3, missing_concepts=()),
        )
        self.assertEqual(decision.strategy, "feedback_then_question")



    def test_explicit_example_change_resets_anchor(self):
        history = [ChatMessage(role="assistant", content=SCENARIO)]
        decision = choose_socratic_strategy("Use a different example.", history, [SOURCE], CLASSIFICATION)
        self.assertIsNone(decision.scenario_anchor)
        history += [ChatMessage(role="user", content="Use a different example."),
                    ChatMessage(role="assistant", content="Suppose your team tests a login feature. Where would you work?")]
        self.assertIn("login feature", conversation_scenario(history))

    def test_topic_change_classification_does_not_reset_scenario(self):
        classification = replace(
            CLASSIFICATION,
            target_concepts=("code review",), target="code review",
        )
        decision = choose_socratic_strategy(
            "what is the code review/",
            [ChatMessage(role="assistant", content=SCENARIO)],
            [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "adaptive_diagnostic")
        self.assertEqual(decision.scenario_anchor, SCENARIO)

    def test_turn_targets_cannot_replace_the_teaching_concept(self):
        classification = replace(
            CLASSIFICATION, target_concepts=("maintainability", "naming conventions"),
            target="maintainability",
        )
        decision = choose_socratic_strategy(
            "Sam can understand Alex's change.",
            [ChatMessage(role="assistant", content="What should Sam examine in Alex's change?")],
            [SOURCE], classification, stable_concept="code review",
        )
        self.assertEqual(decision.target_concept, "code review")
        self.assertIn("Target concept: code review", socratic_system_instruction(decision))

    def test_high_score_does_not_change_the_original_example(self):
        decision = choose_socratic_strategy("I can explain it.", [ChatMessage(role="assistant", content=SCENARIO)], [SOURCE], CLASSIFICATION,
            replace(EVALUATION, progress_status="mastered"))
        self.assertEqual(decision.scenario_anchor, SCENARIO)
        self.assertNotEqual(decision.strategy, "mastery_verification")
