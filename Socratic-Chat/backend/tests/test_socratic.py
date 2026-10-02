from __future__ import annotations

import unittest

from app.schemas import ChatMessage, Source
from app.classifier import MessageClassification
from app.answer_evaluation import AnswerEvaluation
from app.socratic import (
    choose_socratic_strategy,
    socratic_system_instruction,
)


SOURCE = Source(
    document_id="doc-1",
    chunk_id="chunk-1",
    title="use-cases.html",
    text="Actors are outside the system boundary and use cases are inside it.",
    score=0.03,
)


class SocraticPolicyTests(unittest.TestCase):
    def test_question_about_previous_tutor_wording_gets_direct_explanation(self) -> None:
        history = [ChatMessage(role="assistant", content=(
            "Alex explains his bug fix to Sam without changing his original approach. "
            "How can Alex make his logic clear?"
        ))]
        decision = choose_socratic_strategy(
            'what is the "his original approach meaning" in the context', history, [],
        )
        self.assertEqual(decision.mode, "direct")
        self.assertEqual(decision.strategy, "contextual_wording_explanation")
        self.assertIn("substantive tutor turn", decision.instruction)

    def test_persistent_ready_status_selects_mastery_verification(self) -> None:
        evaluation = AnswerEvaluation(
            concept="version control",
            keyword_coverage=1,
            semantic_alignment=0.9,
            rubric_score=0.9,
            total_score=92,
            correctness=4,
            completeness=3,
            reasoning=4,
            application=3,
            supported_concepts=("revision history",),
            missing_concepts=(),
            critical_misconception=False,
            misconception=None,
            feedback="The explanation is well supported.",
            confidence=0.95,
            progress_status="ready_for_verification",
        )
        history = [ChatMessage(role="assistant", content="Why does version control help teams?")]
        decision = choose_socratic_strategy(
            "It preserves shared history and supports collaboration.",
            history,
            [SOURCE],
            answering_classification := MessageClassification(
                conversation_state="answering_tutor",
                dialogue_status="answering_tutor",
                conversation_action="continue",
                target="version control",
            ),
            evaluation,
        )
        self.assertEqual(answering_classification.dialogue_status, "answering_tutor")
        self.assertEqual(decision.strategy, "mastery_verification")
        self.assertEqual(decision.tutor_question_type, "application")

    def test_first_recorded_high_score_does_not_verify_early(self) -> None:
        evaluation = AnswerEvaluation(
            concept="version control", keyword_coverage=1, semantic_alignment=1,
            rubric_score=1, total_score=100, correctness=4, completeness=4,
            reasoning=4, application=4, supported_concepts=(), missing_concepts=(),
            critical_misconception=False, misconception=None, feedback="Correct.",
            confidence=1, progress_status="developing",
        )
        history = [ChatMessage(role="assistant", content="Why does version control help teams?")]
        decision = choose_socratic_strategy(
            "It preserves shared history and supports collaboration.", history, [SOURCE],
            MessageClassification(
                conversation_state="answering_tutor", dialogue_status="answering_tutor",
                conversation_action="continue", target="version control",
            ),
            evaluation,
        )
        self.assertNotEqual(decision.strategy, "mastery_verification")

    def test_assignment_logistics_receive_a_direct_answer(self) -> None:
        decision = choose_socratic_strategy("What are the Assignment 4 requirements?", [], [SOURCE])
        self.assertEqual(decision.mode, "direct")
        self.assertEqual(decision.strategy, "grounded_explanation")
        self.assertEqual(decision.disclosure_level, 4)

    def test_new_concept_question_starts_with_diagnostic_recall(self) -> None:
        decision = choose_socratic_strategy("What is a use case?", [], [SOURCE])
        self.assertEqual(decision.mode, "socratic")
        self.assertEqual(decision.strategy, "diagnostic_recall")
        self.assertEqual(decision.disclosure_level, 0)
        instruction = socratic_system_instruction(decision)
        self.assertIn("Ask exactly one", instruction)
        self.assertIn("Disclosure level 0", instruction)


    def test_uncertainty_receives_a_hint(self) -> None:
        decision = choose_socratic_strategy("I am not sure.", [], [SOURCE])
        self.assertEqual(decision.student_state, "uncertain")
        self.assertEqual(decision.strategy, "scaffold_then_question")
        self.assertEqual(decision.disclosure_level, 2)

    def test_explicit_hint_request_increases_disclosure_to_level_two(self) -> None:
        decision = choose_socratic_strategy("Could I have a hint?", [], [SOURCE])
        self.assertEqual(decision.strategy, "scaffold_then_question")
        self.assertEqual(decision.disclosure_level, 2)


    def test_possible_misconception_uses_guided_comparison(self) -> None:
        decision = choose_socratic_strategy("I thought students should be inside.", [], [SOURCE])
        self.assertEqual(decision.student_state, "possible_misconception")
        self.assertEqual(decision.strategy, "guided_comparison")

    def test_repeated_difficulty_discloses_an_explanation(self) -> None:
        history = [
            ChatMessage(role="assistant", content="Who interacts with the system?"),
            ChatMessage(role="user", content="A student."),
            ChatMessage(role="assistant", content="Is that person part of the software?"),
        ]
        decision = choose_socratic_strategy("I don't know.", history, [SOURCE])
        self.assertEqual(decision.strategy, "explain_then_check")
        self.assertEqual(decision.disclosure_level, 4)
        self.assertIn("Do not withhold", decision.instruction)

    def test_llm_support_level_simplifies_current_example(self) -> None:
        classification = MessageClassification(
            conversation_state="uncertain",
            dialogue_status="uncertain",
            target_concepts=("code review",),
            target="code review",
            understanding_level="beginner",
            support_level=2,
        )
        decision = choose_socratic_strategy(
            "I still do not understand.", [], [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "explain_then_check")
        self.assertEqual(decision.example_type, "simplified_current_example")
        self.assertEqual(decision.disclosure_level, 4)

    def test_no_detected_improvement_selects_a_simpler_example(self) -> None:
        evaluation = AnswerEvaluation(
            concept="code review", keyword_coverage=0.2, semantic_alignment=0.3,
            rubric_score=0.25, total_score=25, correctness=1, completeness=1,
            reasoning=1, application=None, supported_concepts=(),
            missing_concepts=("review purpose",), critical_misconception=False,
            misconception=None, feedback="The purpose is still unclear.", confidence=0.9,
            understanding_improved=False,
        )
        decision = choose_socratic_strategy(
            "It evaluates code.",
            [ChatMessage(role="assistant", content="What is code review intended to improve?")],
            [SOURCE],
            MessageClassification(
                conversation_state="answering_tutor", dialogue_status="answering_tutor",
                target="code review",
            ),
            evaluation,
        )
        self.assertEqual(decision.strategy, "explain_then_check")
        self.assertEqual(decision.example_type, "simplified_current_example")

    def test_missing_sources_does_not_generate_an_ungrounded_question(self) -> None:
        decision = choose_socratic_strategy("What is a use case?", [], [])
        self.assertEqual(decision.mode, "direct")















    def test_classifier_selects_contrasting_examples_for_comparison(self) -> None:
        classification = MessageClassification(
            question_type="comparison",
            target_concepts=("Git", "GitHub"),
            target="Git",
            confidence=0.95,
            source="llm",
        )
        decision = choose_socratic_strategy(
            "How are Git and GitHub different?", [], [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "guided_comparison")
        self.assertEqual(decision.example_type, "contrasting_cases")
        self.assertEqual(decision.tutor_question_type, "comparison")

    def test_opening_definition_uses_example_even_if_status_requests_support(self) -> None:
        classification = MessageClassification(
            route="learning",
            question_type="what",
            conversation_state="new_concept",
            dialogue_status="requesting_support",
            support_level=1,
            target_concepts=("version control",),
            target="version control",
        )
        decision = choose_socratic_strategy(
            "what is the version control", [], [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "diagnostic_recall")
        self.assertEqual(decision.example_type, "familiar_scenario")

    def test_opening_definition_uses_example_even_if_support_is_overestimated(self) -> None:
        classification = MessageClassification(
            route="learning",
            question_type="what",
            conversation_state="requesting_hint",
            dialogue_status="requesting_support",
            support_level=2,
            target="version control",
        )
        decision = choose_socratic_strategy(
            "what is the version control", [], [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "diagnostic_recall")

    def test_explicit_broad_question_overrides_support_continuation(self) -> None:
        history = [
            ChatMessage(role="user", content="What is code review?"),
            ChatMessage(role="assistant", content="What benefit does a reviewer's suggestion provide?"),
            ChatMessage(role="user", content="It gives me another way to build the code."),
        ]
        classification = MessageClassification(
            route="learning",
            question_type="what",
            conversation_state="requesting_answer",
            dialogue_status="requesting_support",
            conversation_action="continue",
            has_substantive_claim=False,
            support_level=1,
            target_concepts=("core skill", "code review"),
            target="core skill",
        )
        decision = choose_socratic_strategy(
            "What is the core skill in the code review?", history, [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "connected_concept_explanation")
        self.assertEqual(decision.mode, "direct")
        self.assertEqual(decision.target_concept, "core skill and code review")



    def test_tutor_instruction_uses_selective_keyword_emphasis(self) -> None:
        decision = choose_socratic_strategy("What is a use case?", [], [SOURCE])
        instruction = socratic_system_instruction(decision)
        self.assertIn("Strongly prefer 40 words or fewer overall", instruction)
        self.assertIn("exceed 40 words only when", instruction)
        self.assertIn("Markdown bold", instruction)
        self.assertIn("Do not bold complete sentences", instruction)
        self.assertIn("final question in its own paragraph", instruction)
        self.assertIn("plain, conversational language", instruction)
        self.assertIn("Do not expose internal question", instruction)


    def test_two_questions_do_not_establish_understanding(self) -> None:
        history = [
            ChatMessage(role="assistant", content="What comes to mind first?"),
            ChatMessage(role="user", content="A user goal."),
            ChatMessage(role="assistant", content="How would you justify that response?"),
            ChatMessage(role="user", content="It describes what the user does."),
        ]
        decision = choose_socratic_strategy("It describes what the user does.", history, [SOURCE])
        self.assertEqual(decision.strategy, "justify_or_refine")

    def test_three_questions_do_not_trigger_synthesis(self) -> None:
        history = [
            ChatMessage(role="assistant", content="What comes to mind first?"),
            ChatMessage(role="user", content="A user goal."),
            ChatMessage(role="assistant", content="What evidence supports that?"),
            ChatMessage(role="user", content="The actor initiates it."),
            ChatMessage(role="assistant", content="What alternative factor matters?"),
            ChatMessage(role="user", content="The boundary also matters."),
        ]
        decision = choose_socratic_strategy("The boundary also matters.", history, [SOURCE])
        self.assertEqual(decision.strategy, "justify_or_refine")

    def test_four_questions_do_not_trigger_completion(self) -> None:
        history = [
            ChatMessage(role="assistant", content="What comes to mind first?"),
            ChatMessage(role="user", content="A user goal."),
            ChatMessage(role="assistant", content="What evidence supports that?"),
            ChatMessage(role="user", content="The actor initiates it."),
            ChatMessage(role="assistant", content="What alternative factor matters?"),
            ChatMessage(role="user", content="The system boundary."),
            ChatMessage(role="assistant", content="How can you combine those ideas?"),
            ChatMessage(role="user", content="Actors connect to use cases."),
        ]
        decision = choose_socratic_strategy("Actors connect to use cases.", history, [SOURCE])
        self.assertEqual(decision.strategy, "justify_or_refine")

    def test_new_concept_resets_the_dialogue_progression(self) -> None:
        history = [
            ChatMessage(role="assistant", content="What comes to mind first?"),
            ChatMessage(role="user", content="A user goal."),
            ChatMessage(role="assistant", content="What evidence supports that?"),
            ChatMessage(role="user", content="The actor initiates it."),
            ChatMessage(role="assistant", content="What alternative factor matters?"),
            ChatMessage(role="user", content="The system boundary."),
        ]
        decision = choose_socratic_strategy("What is encapsulation?", history, [SOURCE])
        self.assertEqual(decision.strategy, "diagnostic_recall")







    def test_bare_understanding_claim_gets_a_verification_task(self) -> None:
        classification = MessageClassification(
            conversation_state="claiming_understanding",
            dialogue_status="claiming_understanding",
            conversation_action="verify_understanding",
            target_concepts=("version control",),
            target="version control",
            confidence=0.96,
            source="llm",
        )
        decision = choose_socratic_strategy("I understand it.", [], [SOURCE], classification)
        self.assertEqual(decision.strategy, "understanding_check")
        self.assertEqual(decision.disclosure_level, 0)
        self.assertIn("self-reported understanding", decision.instruction)


    def test_student_project_reasoning_is_not_forced_into_direct_answer_mode(self) -> None:
        classification = MessageClassification(
            conversation_state="answering_tutor",
            dialogue_status="answering_tutor",
            conversation_action="continue",
            target_concepts=("version control",),
            target="version control",
            confidence=0.9,
            source="llm",
        )
        history = [ChatMessage(role="assistant", content="Why might a team need version control?")]
        decision = choose_socratic_strategy(
            "Perhaps we can build a product or project successfully.", history, [SOURCE], classification,
        )
        self.assertEqual(decision.mode, "socratic")

    def test_instruction_forbids_attributing_retrieved_facts_to_student(self) -> None:
        decision = choose_socratic_strategy("Why does review matter?", [], [SOURCE])
        instruction = socratic_system_instruction(decision)
        self.assertIn("learner identified", instruction)
        self.assertIn("not learner-authored evidence", instruction)

    def test_instruction_gives_specific_positive_feedback_for_nearly_correct_answers(self) -> None:
        history = [ChatMessage(role="assistant", content="Where should actors appear?")]
        decision = choose_socratic_strategy(
            "Actors should be outside because they interact with the system.", history, [SOURCE],
        )
        instruction = socratic_system_instruction(decision)
        self.assertIn("nearly correct response", instruction)
        self.assertIn("on the right track", instruction)
        self.assertIn("do not praise it", instruction)



if __name__ == "__main__":
    unittest.main()
