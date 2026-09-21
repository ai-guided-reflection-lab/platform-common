from __future__ import annotations

import unittest

from app.schemas import ChatMessage, Source
from app.classifier import MessageClassification
from app.answer_evaluation import AnswerEvaluation
from app.socratic import (
    choose_socratic_strategy,
    enforce_socratic_response,
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

    def test_comparison_question_uses_natural_diagnostic_wording(self) -> None:
        question = "What is the difference between software engineering and programming?"
        decision = choose_socratic_strategy(question, [], [SOURCE])
        answer = enforce_socratic_response("A long definition.", question, decision)
        self.assertEqual(
            answer,
            "Before we compare **software engineering** and **programming**, what difference comes to mind first?",
        )

    def test_uncertainty_receives_a_hint(self) -> None:
        decision = choose_socratic_strategy("I am not sure.", [], [SOURCE])
        self.assertEqual(decision.student_state, "uncertain")
        self.assertEqual(decision.strategy, "scaffold_then_question")
        self.assertEqual(decision.disclosure_level, 2)

    def test_explicit_hint_request_increases_disclosure_to_level_two(self) -> None:
        decision = choose_socratic_strategy("Could I have a hint?", [], [SOURCE])
        self.assertEqual(decision.strategy, "scaffold_then_question")
        self.assertEqual(decision.disclosure_level, 2)

    def test_visible_hint_label_is_removed_from_response(self) -> None:
        decision = choose_socratic_strategy("Could you guide me?", [], [SOURCE])
        self.assertEqual(decision.strategy, "scaffold_then_question")
        answer = enforce_socratic_response(
            "**Hint:** Actors interact from outside the boundary.\n\nWhere should a student actor appear?",
            "Could you guide me?",
            decision,
        )
        self.assertNotIn("Hint:", answer)
        self.assertTrue(answer.startswith("Actors interact"))
        self.assertEqual(answer.count("?"), 1)

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
            student_intent="hint",
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

    def test_noncompliant_lecture_is_replaced_by_one_diagnostic_question(self) -> None:
        decision = choose_socratic_strategy("What is mentorship in the paper?", [], [SOURCE])
        lecture = "Mentorship has three benefits:\n- Support\n- Safety\n- Learning"
        answer = enforce_socratic_response(lecture, "What is mentorship in the paper?", decision)
        self.assertEqual(answer.count("?"), 1)
        self.assertIn("mentorship", answer.lower())
        self.assertNotIn("three benefits", answer)

    def test_diagnostic_turn_rejects_a_definition_disguised_as_a_question(self) -> None:
        decision = choose_socratic_strategy("What is software engineering?", [], [SOURCE])
        model_answer = (
            "Software engineering includes policies, practices, tools, time, scale, and sustainability. "
            "How do you think sustainability affects software engineering practices?"
        )
        answer = enforce_socratic_response(model_answer, "What is software engineering?", decision)
        self.assertIn("Imagine a team", answer)
        self.assertNotIn("policies", answer)

    def test_short_example_first_diagnostic_is_preserved(self) -> None:
        decision = choose_socratic_strategy("What is version control?", [], [SOURCE])
        candidate = (
            "Imagine two developers change the same file on separate laptops and need to combine their work. "
            "What problem should their tool help them solve?"
        )
        answer = enforce_socratic_response(candidate, "What is version control?", decision)
        self.assertEqual(answer, candidate)

    def test_definition_misclassified_as_direct_still_starts_with_scenario(self) -> None:
        classification = MessageClassification(
            route="learning",
            student_intent="direct_answer",
            question_type="what",
            target_concepts=("code review",),
            target="code review",
            conversation_state="requesting_answer",
            conversation_action="direct",
            source="llm",
        )
        decision = choose_socratic_strategy("what is the code review", [], [SOURCE], classification)
        answer = enforce_socratic_response(
            "Code review is a process where another developer examines code for correctness.",
            "what is the code review",
            decision,
        )
        self.assertEqual(decision.strategy, "diagnostic_recall")
        self.assertTrue(answer.startswith("Imagine"))
        self.assertNotIn("is a process", answer)

    def test_version_control_diagnostic_fallback_uses_concrete_shared_file_scenario(self) -> None:
        decision = choose_socratic_strategy("what is the version control", [], [SOURCE])
        answer = enforce_socratic_response(
            "Version control tracks changes and coordinates developers.",
            "what is the version control",
            decision,
        )
        self.assertIn("two developers", answer)
        self.assertIn("same file", answer)
        self.assertIn("shared project", answer)
        self.assertNotIn("encounters **version control**", answer)

    def test_classifier_selects_contrasting_examples_for_comparison(self) -> None:
        classification = MessageClassification(
            student_intent="comparison",
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

    def test_question_that_depends_on_removed_preamble_uses_self_contained_fallback(self) -> None:
        decision = choose_socratic_strategy("What is software engineering?", [], [SOURCE])
        model_answer = (
            "Software engineering considers time, scale, and sustainability. "
            "Where do you think these factors affect a software project?"
        )
        answer = enforce_socratic_response(model_answer, "What is software engineering?", decision)
        self.assertNotIn("these factors", answer.lower())
        self.assertIn("software engineering", answer.lower())
        self.assertEqual(answer.count("?"), 1)

    def test_multiple_model_questions_are_replaced_by_diagnostic_opening(self) -> None:
        decision = choose_socratic_strategy("What is mentorship?", [], [SOURCE])
        answer = enforce_socratic_response(
            "What do you already know? Can you give an example?",
            "What is mentorship?",
            decision,
        )
        self.assertIn("Imagine a team", answer)
        self.assertIn("**mentorship**", answer)
        self.assertEqual(answer.count("?"), 1)

    def test_tutor_instruction_uses_selective_keyword_emphasis(self) -> None:
        decision = choose_socratic_strategy("What is a use case?", [], [SOURCE])
        instruction = socratic_system_instruction(decision)
        self.assertIn("Markdown bold", instruction)
        self.assertIn("Do not bold complete sentences", instruction)
        self.assertIn("final question in its own paragraph", instruction)
        self.assertIn("plain, conversational language", instruction)
        self.assertIn("Do not expose internal question", instruction)

    def test_explanation_is_preserved_after_repeated_difficulty(self) -> None:
        history = [
            ChatMessage(role="assistant", content="What do you think?"),
            ChatMessage(role="user", content="I am unsure."),
            ChatMessage(role="assistant", content="Which detail helps?"),
        ]
        decision = choose_socratic_strategy("I still don't know.", history, [SOURCE])
        answer = enforce_socratic_response("Actors remain outside the boundary.", "I still don't know.", decision)
        self.assertIn("Actors remain outside", answer)
        self.assertEqual(answer.count("?"), 1)

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

    def test_level_one_feedback_is_capped_at_twelve_words(self) -> None:
        history = [ChatMessage(role="assistant", content="What comes to mind first?")]
        decision = choose_socratic_strategy("It seems related to a user goal.", history, [SOURCE])
        answer = enforce_socratic_response(
            "Your response correctly identifies a very important relationship between the external actor and the internal system behavior in this example.\n\n"
            "What evidence supports your response?",
            "It seems related to a user goal.",
            decision,
        )
        feedback, question = answer.split("\n\n", 1)
        self.assertLessEqual(len(feedback.split()), 12)
        self.assertEqual(question, "Which detail from the course example would make your answer more precise?")

    def test_question_over_twenty_five_words_uses_strategy_fallback(self) -> None:
        history = [ChatMessage(role="assistant", content="What comes to mind first?")]
        decision = choose_socratic_strategy("It seems related to a user goal.", history, [SOURCE])
        long_question = (
            "What evidence from every section of the retrieved course material would you use to explain in extensive "
            "detail why your current response should be accepted as completely correct by another student?"
        )
        answer = enforce_socratic_response(long_question, "It seems related to a user goal.", decision)
        self.assertEqual(answer, "Which detail from the course example would make your answer more precise?")

    def test_substantive_passage_gets_neutral_reflection_before_plain_question(self) -> None:
        passage = (
            "Simplicity has a tension with workflow integration. Critique keeps code review as its primary focus "
            "while linking features implemented in other subsystems."
        )
        classification = MessageClassification(
            student_intent="reflection",
            conversation_state="follow_up",
            dialogue_status="unclear",
            target="simplicity and workflow integration",
        )
        decision = choose_socratic_strategy(passage, [], [SOURCE], classification)
        self.assertEqual(decision.strategy, "reflect_then_explore")
        answer = enforce_socratic_response(
            "Which scenario** better reflects the tension between *simplicity* and *workflow integration*?",
            passage,
            decision,
        )
        reflection, question = answer.split("\n\n", 1)
        self.assertIn("choice", reflection.lower())
        self.assertNotIn("Which scenario", answer)
        self.assertEqual(answer.count("?"), 1)
        self.assertTrue(question.startswith("Why might"))

    def test_generic_academic_question_stem_is_replaced_with_plain_wording(self) -> None:
        history = [ChatMessage(role="assistant", content="Why might review help a team?")]
        decision = choose_socratic_strategy("Because teammates can find mistakes.", history, [SOURCE])
        answer = enforce_socratic_response(
            "That connects review with finding mistakes.\n\nWhat evidence supports that reasoning?",
            "Because teammates can find mistakes.",
            decision,
        )
        self.assertNotIn("What evidence", answer)
        self.assertIn("Which detail from the course example", answer)

    def test_bare_understanding_claim_gets_a_verification_task(self) -> None:
        classification = MessageClassification(
            student_intent="comprehension_claim",
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

    def test_confirmation_claim_gets_grounded_feedback_before_one_question(self) -> None:
        classification = MessageClassification(
            student_intent="confirmation",
            dialogue_status="requesting_confirmation",
            conversation_action="verify_claim",
            has_substantive_claim=True,
            student_claim="Actors belong inside the system boundary.",
            target_concepts=("system boundary",),
            target="system boundary",
            confidence=0.98,
            source="llm",
        )
        decision = choose_socratic_strategy(
            "Actors belong inside the system boundary. Is that right?", [], [SOURCE], classification,
        )
        self.assertEqual(decision.strategy, "grounded_claim_check")
        answer = enforce_socratic_response(
            "Not quite—actors remain outside the boundary.",
            "Actors belong inside the system boundary. Is that right?",
            decision,
        )
        self.assertIn("Not quite", answer)
        self.assertEqual(answer.count("?"), 1)

    def test_student_project_reasoning_is_not_forced_into_direct_answer_mode(self) -> None:
        classification = MessageClassification(
            student_intent="reflection",
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

    def test_specific_positive_feedback_is_preserved_before_next_question(self) -> None:
        history = [ChatMessage(role="assistant", content="Where should actors appear?")]
        message = "Actors should be outside because they interact with the system."
        decision = choose_socratic_strategy(message, history, [SOURCE])
        answer = enforce_socratic_response(
            "You correctly connected actors with interaction outside the boundary.\n\n"
            "What evidence explains why use cases belong inside?",
            message,
            decision,
        )
        feedback, question = answer.split("\n\n", 1)
        self.assertIn("correctly connected", feedback)
        self.assertEqual(answer.count("?"), 1)
        self.assertTrue(question.endswith("?"))


if __name__ == "__main__":
    unittest.main()
