from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.schemas import ChatMessage, Source

if TYPE_CHECKING:
    from app.answer_evaluation import AnswerEvaluation
    from app.classifier import MessageClassification


DIRECT_INFORMATION_PATTERN = re.compile(
    r"\b(?:assignment|rubric|deadline|due date|submission|submit|points?|grade|"
    r"office hours?|schedule|syllabus|uploaded files?|documents?)\b",
    re.IGNORECASE,
)
PROJECT_INFORMATION_PATTERN = re.compile(
    r"^(?:what|explain|describe|summarize|tell me|give me)\b.*\bprojects?\b",
    re.IGNORECASE,
)
DIRECT_REQUEST_PATTERN = re.compile(
    r"\b(?:just tell me|give me the answer|answer directly|no questions?|"
    r"stop asking|explain it directly)\b",
    re.IGNORECASE,
)
HINT_REQUEST_PATTERN = re.compile(
    r"\b(?:hint|small clue|give me a clue|nudge me|help me start|guide me)\b",
    re.IGNORECASE,
)
UNCERTAINTY_PATTERN = re.compile(
    r"\b(?:i (?:still )?(?:do not|don't) know|not sure|unsure|confused|no idea|i'm stuck|i am stuck)\b",
    re.IGNORECASE,
)
MISCONCEPTION_PATTERN = re.compile(
    r"\b(?:i thought|isn't it|is it not|but i think|shouldn't|cannot be|can't be)\b",
    re.IGNORECASE,
)
REASONING_PATTERN = re.compile(r"\b(?:because|therefore|since|which means|so that)\b", re.IGNORECASE)
VISIBLE_HINT_LABEL_PATTERN = re.compile(
    r"^\s*(?:\*\*(?:hint|clue):\*\*|__(?:hint|clue):__|(?:hint|clue):)\s*",
    re.IGNORECASE,
)
NEW_CONCEPT_PATTERN = re.compile(
    r"^(?:what is|what are|define|explain|tell me about|help me understand)\b",
    re.IGNORECASE,
)
GENERIC_VISIBLE_QUESTION_PATTERN = re.compile(
    r"^(?:\*{0,2})?(?:what evidence|what factors?|which assumptions?|what consequences?|"
    r"what implications?|what limitations?|what alternative(?: viewpoint| factor)?s?)\b",
    re.IGNORECASE,
)
INCOMPLETE_CHOICE_PATTERN = re.compile(r"^(?:\*{0,2})?which (?:scenario|example|option)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SocraticDecision:
    mode: str
    student_state: str
    strategy: str
    instruction: str
    disclosure_level: int = 1
    target_concept: str | None = None
    example_type: str = "none"
    tutor_question_type: str = "clarification"


DIRECT_DECISION = SocraticDecision(
    mode="direct",
    student_state="information_request",
    strategy="grounded_explanation",
    instruction=(
        "Answer the request directly and concisely from the retrieved context. "
        "Do not force a Socratic question into administrative or assignment-logistics information."
    ),
    disclosure_level=4,
)


def _recent_socratic_questions(history: list[ChatMessage]) -> int:
    recent_history = history[-10:]
    for index in range(len(recent_history) - 1, -1, -1):
        message = recent_history[index]
        if message.role == "assistant" and message.content.lstrip().startswith("Before we define"):
            recent_history = recent_history[index:]
            break
    return sum(
        1
        for message in recent_history
        if message.role == "assistant" and message.content.rstrip().endswith("?")
    )


def choose_socratic_strategy(
    message: str,
    history: list[ChatMessage],
    sources: list[Source],
    classification: MessageClassification | None = None,
    evaluation: AnswerEvaluation | None = None,
) -> SocraticDecision:
    """Choose one explainable teaching action after document retrieval."""
    clean_message = " ".join(message.strip().split())
    if not sources:
        return DIRECT_DECISION
    if classification:
        direct_request = (
            classification.route == "administrative"
            or classification.student_intent == "direct_answer"
            or classification.conversation_action == "direct"
        )
    else:
        direct_request = bool(
            DIRECT_INFORMATION_PATTERN.search(clean_message)
            or PROJECT_INFORMATION_PATTERN.search(clean_message)
            or DIRECT_REQUEST_PATTERN.search(clean_message)
        )
    if direct_request:
        return DIRECT_DECISION

    question_turns = _recent_socratic_questions(history)
    if classification and len(classification.target_concepts) > 1:
        target = " and ".join(classification.target_concepts)
    else:
        target = (
            classification.target
            if classification and classification.target
            else _target_concept(clean_message)
        )
    intent = classification.student_intent if classification else None
    classified_state = classification.conversation_state if classification else None
    conversation_action = classification.conversation_action if classification else "continue"
    support_level = classification.support_level if classification else 0

    needs_verification = bool(
        evaluation
        and (
            evaluation.progress_status == "ready_for_verification"
            or (
                evaluation.progress_status == "unrecorded"
                and evaluation.ready_for_verification
            )
        )
    )
    if evaluation and needs_verification:
        return SocraticDecision(
            mode="socratic",
            student_state="ready_for_verification",
            strategy="mastery_verification",
            instruction=(
                "Give one specific positive observation about the demonstrated reasoning. Do not declare mastery. "
                "Ask exactly one short transfer, prediction, or teach-back question that requires an independently "
                "demonstrated answer in a new situation."
            ),
            disclosure_level=1,
            target_concept=target,
            example_type="transfer_check",
            tutor_question_type="application",
        )

    if conversation_action == "verify_claim":
        return SocraticDecision(
            mode="socratic",
            student_state="requesting_confirmation",
            strategy="grounded_claim_check",
            instruction=(
                "Compare only the learner's actual claim with the retrieved context. Begin with exactly one "
                "calibrated verdict: 'Yes—', 'Partly—', or 'Not quite—'. Briefly state the supported point or "
                "smallest necessary correction, then ask exactly one question inviting revision or application. "
                "Never attribute a retrieved fact to the learner unless it appears in the learner's message."
            ),
            disclosure_level=3,
            target_concept=target,
            example_type="claim_check",
            tutor_question_type="clarification",
        )

    if conversation_action == "verify_understanding":
        return SocraticDecision(
            mode="socratic",
            student_state="claiming_understanding",
            strategy="understanding_check",
            instruction=(
                "Treat the learner's statement as self-reported understanding, not demonstrated understanding. "
                "Give no congratulatory evaluation yet. Present one brief transfer, prediction, comparison, or "
                "teach-back task grounded in the retrieved context and ask exactly one verification question."
            ),
            disclosure_level=0,
            target_concept=target,
            example_type="verification_task",
            tutor_question_type="application",
        )

    if (evaluation and evaluation.understanding_improved is False) or (
        classification and support_level >= 2
    ):
        return SocraticDecision(
            mode="socratic",
            student_state="repeated_difficulty",
            strategy="explain_then_check",
            instruction=(
                "Give a concise, evidence-grounded explanation now and a concrete example that is simpler and "
                "meaningfully different from examples already used in the conversation. If support level is 3, "
                "walk through that example step by step. Then ask exactly one easy, specific check question. "
                "Do not withhold the explanation again and do not repeat the previous question."
            ),
            disclosure_level=4,
            target_concept=target,
            example_type="simpler_new_example",
            tutor_question_type="application",
        )

    if (
        intent == "hint" or (classification is None and HINT_REQUEST_PATTERN.search(clean_message))
    ) and support_level < 2:
        return SocraticDecision(
            mode="socratic",
            student_state="support_requested",
            strategy="scaffold_then_question",
            instruction=(
                "Offer one brief contextual clue naturally, grounded in the retrieved context, without revealing "
                "the entire answer. Do not introduce it with a label. Then ask exactly one focused question."
            ),
            disclosure_level=2,
            target_concept=target,
            example_type="simplified_example",
            tutor_question_type="application",
        )

    if intent == "comparison":
        return SocraticDecision(
            mode="socratic",
            student_state="prior_knowledge_unknown",
            strategy="guided_comparison",
            instruction=(
                "Give two short contrasting situations grounded in the retrieved context without stating the "
                "final distinction. Then ask exactly one question that invites the learner to identify it."
            ),
            disclosure_level=0,
            target_concept=target,
            example_type="contrasting_cases",
            tutor_question_type="comparison",
        )

    if intent in {"procedure", "application", "debugging"}:
        strategy_by_intent = {
            "procedure": "guided_sequence",
            "application": "transfer_application",
            "debugging": "failure_scenario",
        }
        return SocraticDecision(
            mode="socratic",
            student_state="prior_knowledge_unknown",
            strategy=strategy_by_intent[intent],
            instruction=(
                "Present one short, concrete scenario grounded in the retrieved context, leaving one meaningful "
                "step or decision unresolved. Ask exactly one question that lets the learner complete it."
            ),
            disclosure_level=0,
            target_concept=target,
            example_type="incomplete_scenario",
            tutor_question_type="application",
        )

    if (
        classification is None and NEW_CONCEPT_PATTERN.search(clean_message)
    ) or (intent in {"definition", "explanation"} and classified_state == "new_concept"):
        return SocraticDecision(
            mode="socratic",
            student_state="prior_knowledge_unknown",
            strategy="diagnostic_recall",
            instruction=(
                "Do not lecture or state the definition. Give one brief, familiar scenario grounded in the "
                "retrieved context. Ask exactly one accessible question that helps the learner notice the idea."
            ),
            disclosure_level=0,
            target_concept=target,
            example_type="familiar_scenario",
            tutor_question_type="clarification" if intent != "explanation" else "implication",
        )

    if classified_state == "uncertain" or (
        classification is None and UNCERTAINTY_PATTERN.search(clean_message)
    ):
        if classification is None and question_turns >= 2:
            return SocraticDecision(
                mode="socratic",
                student_state="repeated_difficulty",
                strategy="explain_then_check",
                instruction=(
                    "Give a concise, evidence-grounded explanation now and a concrete example that is simpler and "
                    "meaningfully different from examples already used in the conversation. If support level is 3, "
                    "walk through that example step by step. Then ask exactly one easy, specific check question. "
                    "Do not withhold the explanation again and do not repeat the previous question."
                ),
                disclosure_level=4,
                target_concept=target,
                example_type="simpler_new_example",
                tutor_question_type="application",
            )
        return SocraticDecision(
            mode="socratic",
            student_state="uncertain",
            strategy="scaffold_then_question",
            instruction=(
                "Offer one brief contextual clue naturally, grounded in the retrieved context, without revealing "
                "the entire answer. Do not introduce it with a label. Then ask exactly one focused question."
            ),
            disclosure_level=2,
            target_concept=target,
            example_type="simplified_example",
            tutor_question_type="application",
        )

    if classified_state == "possible_misconception" or (
        classification is None and MISCONCEPTION_PATTERN.search(clean_message)
    ):
        return SocraticDecision(
            mode="socratic",
            student_state="possible_misconception",
            strategy="guided_comparison",
            instruction=(
                "Briefly acknowledge the learner's idea without calling it correct or incorrect. Ask exactly one "
                "guided-comparison question that helps distinguish the two relevant concepts."
            ),
            target_concept=target,
            example_type="counterexample",
            tutor_question_type="alternative",
        )

    if classified_state == "reasoning_in_progress" or (
        classification is None and REASONING_PATTERN.search(clean_message)
    ):
        return SocraticDecision(
            mode="socratic",
            student_state="reasoning_in_progress",
            strategy="probe_reasoning",
            instruction=(
                "Evaluate the learner's reasoning against the retrieved context. If it is correct or substantially "
                "close, briefly identify the specific valid connection. Then ask exactly one plain-language "
                "question naming a concrete detail, action, or outcome from the course example."
            ),
            target_concept=target,
            example_type="none",
            tutor_question_type="evidence",
        )

    latest_assistant = next((item for item in reversed(history) if item.role == "assistant"), None)
    if latest_assistant and latest_assistant.content.rstrip().endswith("?"):
        if question_turns >= 4:
            return SocraticDecision(
                mode="socratic",
                student_state="ready_to_reflect",
                strategy="reflect_on_learning",
                instruction=(
                    "Give one specific, calibrated observation about the learner's progress, positively recognizing "
                    "any supported reasoning. Then ask exactly one reflection question about how their understanding "
                    "changed or what they would revise."
                ),
            )
        if question_turns == 3:
            return SocraticDecision(
                mode="socratic",
                student_state="ready_to_synthesize",
                strategy="synthesize_understanding",
                instruction=(
                    "Give specific, calibrated feedback in one short sentence, positively recognizing the supported "
                    "part of a correct or nearly correct response. Then ask exactly one question that requires the "
                    "learner to combine relevant concepts or evidence into an overall explanation."
                ),
            )
        if question_turns == 2:
            return SocraticDecision(
                mode="socratic",
                student_state="understanding_developing",
                strategy="examine_limitation",
                instruction=(
                    "Give specific, calibrated feedback in one short sentence, positively recognizing the supported "
                    "part of a correct or nearly correct response. Then name a concrete condition and ask how it "
                    "could change the result the learner described."
                ),
            )
        return SocraticDecision(
            mode="socratic",
            student_state="response_to_prompt",
            strategy="justify_or_refine",
            instruction=(
                "Assess the response against the retrieved context. If it is correct or substantially close, give "
                "specific positive feedback in one short sentence naming the supported part. If it is not close, "
                "respond neutrally. Then ask exactly one question that helps the learner justify or refine it."
            ),
        )

    if _word_count(clean_message) >= 20:
        return SocraticDecision(
            mode="socratic",
            student_state="substantive_passage",
            strategy="reflect_then_explore",
            instruction=(
                "Begin with one short, neutral sentence that names the concrete idea or tradeoff in the learner's "
                "passage without praising it or treating quoted material as demonstrated understanding. Then ask "
                "one plain-language question about a specific action, choice, or outcome named in that passage."
            ),
            disclosure_level=1,
            target_concept=target,
            example_type="passage_reflection",
            tutor_question_type="clarification",
        )

    return SocraticDecision(
        mode="socratic",
        student_state="prior_knowledge_unknown",
        strategy="diagnostic_recall",
        instruction=(
            "Do not lecture or state the definition. Give one brief, familiar scenario grounded in the retrieved "
            "context, then ask exactly one accessible question that helps the learner notice the idea."
        ),
        disclosure_level=0,
        target_concept=target,
        example_type="familiar_scenario",
        tutor_question_type="clarification",
    )


def _disclosure_instruction(level: int) -> str:
    instructions = {
        0: (
            "Disclosure level 0: do not state the definition or conclusion. You may provide one short illustrative "
            "scenario followed by one question; keep the entire response within 60 words."
        ),
        1: (
            "Disclosure level 1: feedback may only reflect the learner's own reasoning in at most 12 words. "
            "Do not add a definition or new course fact. Ask a question of at most 25 words."
        ),
        2: (
            "Disclosure level 2: provide one concise supporting fact naturally, containing at most one new course "
            "fact and at most 18 words, then ask a question of at most 25 words. Never prefix it with 'Hint:'."
        ),
        3: (
            "Disclosure level 3: give a partial grounded explanation of at most 35 words, not the full solution, "
            "then ask a question of at most 25 words."
        ),
        4: (
            "Disclosure level 4: give a clear grounded explanation and one simple, concrete example in at most 80 "
            "words, then ask one easy check question of at most 25 words."
        ),
    }
    return instructions.get(level, "Answer directly and concisely from the retrieved context.")


def socratic_system_instruction(decision: SocraticDecision) -> str:
    emphasis_instruction = (
        "Use Markdown bold for one to three short, important concept terms when emphasis helps the learner. "
        "Do not bold complete sentences or routine conversational words."
    )
    if decision.mode == "direct":
        return f"{decision.instruction} {emphasis_instruction}"
    return (
        "The teaching objective is for the learner to understand and use the instructor-published topic, not merely "
        "to prolong the dialogue or ask another question. "
        f"Socratic teaching state: {decision.student_state}. Strategy: {decision.strategy}. "
        f"Target concept: {decision.target_concept or 'infer from the latest message'}. "
        f"Example pattern: {decision.example_type}. Tutor question type: {decision.tutor_question_type}. "
        f"{decision.instruction} {_disclosure_instruction(decision.disclosure_level)} Ask only one question. "
        "Anchor feedback and questions in the retrieved learning context and the learner's latest response. "
        "Calibrate feedback to the evidence: for a correct response, briefly name what the learner connected "
        "correctly; for a nearly correct response, say they are on the right track and name only the supported part; "
        "for an unsupported or incorrect response, do not praise it. Positive feedback must be specific, concise, "
        "and proportional—it must not imply complete mastery. "
        "Put the final question in its own paragraph. Write it in plain, conversational language and name the "
        "specific action, decision, example, or outcome the learner should examine. Do not expose internal question "
        "categories through canned stems such as 'What evidence', 'What factor', 'Which assumption', 'What "
        "implication', or 'What alternative viewpoint'. If asking the learner to choose a scenario, include the "
        "actual scenarios in the response. The question must make sense by itself without hidden context. "
        "Use specific feedback instead of generic praise such as 'Excellent' or 'Good job'. "
        "Never say the learner identified, explained, or noted a fact unless that fact appears explicitly in the "
        "learner's latest response. Retrieved context is reference evidence, not learner-authored evidence. "
        f"Never invent course facts beyond the retrieved context. {emphasis_instruction}"
    )


def _target_concept(message: str) -> str:
    normalized = " ".join(message.strip().rstrip("?.!").split())
    patterns = [
        r"^(?:what is|what are|define|explain(?:\s+what)?)\s+(.+)$",
        r"^(?:tell me about|help me understand)\s+(.+)$",
    ]
    target = normalized
    for pattern in patterns:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            target = match.group(1)
            break
    target = re.split(r"\s+(?:in|from|according to)\s+(?:the|this|our)\b", target, maxsplit=1, flags=re.IGNORECASE)[0]
    target = re.sub(r"\s+(?:is|are)$", "", target, flags=re.IGNORECASE)
    target = re.sub(r"^(?:the|a|an)\s+", "", target, flags=re.IGNORECASE)
    return target.strip() or "this concept"


def _comparison_targets(message: str) -> tuple[str, str] | None:
    normalized = " ".join(message.strip().rstrip("?.!").split())
    match = re.search(r"\bdifference between (.+?) and (.+)$", normalized, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def socratic_fallback_question(message: str, decision: SocraticDecision) -> str:
    target = _visible_target(decision.target_concept or _target_concept(message))
    if decision.strategy == "diagnostic_recall":
        comparison = _comparison_targets(message)
        if comparison:
            first, second = comparison
            question = f"Before we compare **{first}** and **{second}**, what difference comes to mind first?"
        else:
            question = (
                f"Imagine a team encounters **{target}** while building a project. "
                "What problem do you think it might help them solve?"
            )
        if _word_count(question) <= 60:
            return question
        return "What do you already understand about **this concept**?"
    if decision.strategy == "guided_comparison":
        return f"How would **{target}** behave differently in the two situations?"
    if decision.strategy in {"guided_sequence", "transfer_application", "failure_scenario"}:
        return f"In a simple project scenario, what would you try first with **{target}**, and why?"
    if decision.strategy == "understanding_check":
        return f"How would you apply **{target}** in a new situation to demonstrate your understanding?"
    if decision.strategy == "mastery_verification":
        return f"How would you apply **{target}** in a different situation and explain your reasoning?"
    if decision.strategy == "grounded_claim_check":
        return f"How would you restate your idea about **{target}** after comparing it with the course example?"
    if decision.strategy == "scaffold_then_question":
        return f"Which detail about **{target}** helps you take the next step?"
    if decision.strategy == "probe_reasoning":
        return "Which detail from the course example best supports your answer?"
    if decision.strategy == "justify_or_refine":
        return "Which detail from the course example would make your answer more precise?"
    if decision.strategy == "examine_limitation":
        return f"When might **{target}** work differently from the way you described?"
    if decision.strategy == "synthesize_understanding":
        return f"How would you explain the main parts of **{target}** together in your own words?"
    if decision.strategy == "reflect_on_learning":
        return f"What would you change in your first explanation of **{target}** now?"
    if decision.strategy == "reflect_then_explore":
        return (
            f"This passage presents a choice involving **{target}**.\n\n"
            "Why might someone choose one approach instead of combining both?"
        )
    if decision.strategy == "explain_then_check":
        return "How would you apply **this idea** in a simple example?"
    return f"How would you apply {target} in a new example?"


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _visible_target(target: str, limit: int = 8) -> str:
    clean = " ".join(target.replace("**", "").replace("*", "").split())
    words = clean.split()
    if len(words) > limit:
        clean = " ".join(words[:limit]).rstrip(".,;:") + "…"
    return clean or "this course idea"


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]).rstrip(".,;:") + "…"


def _split_feedback_and_question(answer: str) -> tuple[str, str]:
    question_end = answer.find("?") + 1
    through_question = answer[:question_end].strip()
    boundaries = [
        (through_question.rfind("\n"), 1, False),
        (through_question.rfind(". "), 2, True),
        (through_question.rfind("! "), 2, True),
    ]
    position, width, includes_punctuation = max(boundaries, key=lambda item: item[0])
    if position < 0:
        return "", through_question
    feedback_end = position + 1 if includes_punctuation else position
    feedback = through_question[:feedback_end].strip()
    question = through_question[position + width:].strip()
    return feedback, question


def enforce_socratic_response(answer: str, message: str, decision: SocraticDecision) -> str:
    """Guarantee that a Socratic turn contains exactly one focused question."""
    clean_answer = VISIBLE_HINT_LABEL_PATTERN.sub("", answer.strip(), count=1).strip()
    if decision.mode == "direct":
        return clean_answer

    question_count = clean_answer.count("?")
    target = re.escape((decision.target_concept or _target_concept(message)).strip("* "))
    reveals_definition = bool(
        re.search(
            rf"\b{target}\b\s+(?:is|means|refers to|includes|describes|can be defined as)\b",
            clean_answer,
            re.IGNORECASE,
        )
    )
    depends_on_unexplained_preamble = bool(
        re.search(r"\b(?:these|those|such|the above|this idea|that idea|these factors)\b", clean_answer, re.IGNORECASE)
    )
    valid_example_first_turn = (
        decision.disclosure_level == 0
        and decision.example_type != "none"
        and question_count == 1
        and clean_answer.endswith("?")
        and _word_count(clean_answer) <= 60
        and not reveals_definition
        and not depends_on_unexplained_preamble
        and not re.search(r"(?:^|\n)\s*[-*]\s+", clean_answer)
    )
    if valid_example_first_turn:
        feedback, question = _split_feedback_and_question(clean_answer)
        incomplete_choice = bool(INCOMPLETE_CHOICE_PATTERN.search(question))
        malformed_bold = clean_answer.count("**") % 2 != 0
        if incomplete_choice or malformed_bold or GENERIC_VISIBLE_QUESTION_PATTERN.search(question):
            valid_example_first_turn = False
    if valid_example_first_turn:
        return clean_answer

    if decision.strategy == "diagnostic_recall":
        return socratic_fallback_question(message, decision)

    strict_discovery = decision.strategy in {"diagnostic_recall", "guided_comparison"}
    if strict_discovery and question_count:
        # Early discovery must not reveal the answer before asking the learner
        # to reason. Retain only the first question sentence, discarding any
        # model-generated definition, summary, or bullet list before it.
        question_end = clean_answer.index("?") + 1
        question_start = max(
            clean_answer.rfind(".", 0, question_end),
            clean_answer.rfind("!", 0, question_end),
            clean_answer.rfind("\n", 0, question_end),
        ) + 1
        question_only = clean_answer[question_start:question_end].strip(" -*\t\n")
        depends_on_removed_context = re.search(
            r"\b(?:these|those|such|the above|this idea|that idea)\b",
            question_only,
            re.IGNORECASE,
        )
        if 3 <= _word_count(question_only) <= 25 and not depends_on_removed_context:
            return question_only
        return socratic_fallback_question(message, decision)

    if question_count == 0:
        fallback = socratic_fallback_question(message, decision)
        if decision.strategy in {"explain_then_check", "grounded_claim_check"} and clean_answer:
            clean_answer = f"{clean_answer}\n\n{fallback}"
        else:
            clean_answer = fallback
    elif question_count > 1:
        # Keep only the first complete question so the learner has one clear task.
        clean_answer = clean_answer.split("?", 1)[0].strip() + "?"

    feedback, question = _split_feedback_and_question(clean_answer)
    if (
        not question
        or _word_count(question) > 25
        or GENERIC_VISIBLE_QUESTION_PATTERN.search(question)
        or INCOMPLETE_CHOICE_PATTERN.search(question)
        or question.count("**") % 2 != 0
    ):
        question = socratic_fallback_question(message, decision)

    feedback_limits = {0: 0, 1: 12, 2: 18, 3: 35, 4: 80}
    feedback_limit = feedback_limits.get(decision.disclosure_level, 0)
    if feedback_limit == 0:
        feedback = ""
    elif _word_count(feedback) > feedback_limit:
        feedback = _truncate_words(feedback, feedback_limit)

    return f"{feedback}\n\n{question}".strip()
