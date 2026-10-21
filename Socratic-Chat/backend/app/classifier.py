from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any

from app import settings
from app.keyword_scope import keyword_scope_instruction
from app.llm_client import chat_completion
from app.pipeline_logging import (
    debug_preview,
    log_event,
    log_exception,
    update_llm_request_snapshot,
    write_llm_request_snapshot,
)
from app.schemas import ChatMessage, ClarificationOption


# One observation describes the student's communicative role.  Python maps
# this role to routing, evaluation eligibility, and the next controller action
# so the model cannot issue several contradictory control instructions.
MESSAGE_ROLES = {
    "learning_question",      # Starts a course concept or asks a substantive question.
    "student_answer",         # Attempts to answer the tutor, whether right or wrong.
    "support_request",        # Asks for a hint, simpler wording, or says they are stuck.
    "direct_answer_request",  # Explicitly asks the tutor to answer instead of questioning.
    "follow_up",              # Asks about wording or an idea already in the exchange.
    "confirmation_request",   # Offers a claim and explicitly asks whether it is correct.
    "understanding_claim",    # Says they understand without demonstrating it.
    "acknowledgement",        # Briefly acknowledges the tutor without adding evidence.
    "closing",                # Clearly ends the learning session.
    "topic_change",           # Requests a different primary learning objective.
    "administrative",         # Requests course/application information.
    "ambiguous",              # Context cannot establish the intended referent or task.
}
CLARIFICATION_OPTION_ROLES = {
    "student_answer",
    "support_request",
    "direct_answer_request",
    "follow_up",
    "confirmation_request",
    "understanding_claim",
}
# Administrative requests that can be answered from course/application state.
# "none" means the message should continue through the learning pipeline.
OPERATIONAL_REQUESTS = {
    "none",                 # No operational lookup is requested.
    "list_documents",       # Student asks which documents are available.
    "document_visibility",  # Student asks whether a particular file is visible.
    "document_overview",    # Student asks for an overview of published files.
    "course_title",         # Student asks for the course's name.
    "course_instructor",    # Student asks who teaches the course.
    "course_scope",         # Student asks what this course/chat covers.
    "system_status",        # Student asks whether the application is working.
}
# Ignore these common linking/question words when checking whether an LLM-made
# retrieval subquery still contains a meaningful term from the student's text.
QUERY_STOP_WORDS = {
    "about", "after", "from", "into", "with",  # Common relationships, not a topic.
    "also", "like", "more", "other",            # Modifiers shared by unrelated topics.
    "could", "does", "have", "would",            # Helper verbs in many questions.
    "that", "their", "them", "there", "these", "this", "your",  # Context words needing a noun.
    "what", "when", "where", "which",            # Question words, not course concepts.
}

# The provider must return one structured JSON object. The schema prevents
# arbitrary labels from silently becoming routing instructions.
CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",  # The model response must be a JSON object, not prose.
    "properties": {
        "message_role": {"type": "string", "enum": sorted(MESSAGE_ROLES)},
        "target_concepts": {
            "type": "array",  # A comparison can have more than one concept.
            "items": {"type": "string", "maxLength": 100},  # Bound each concept label.
        },
        "missing_context": {"type": ["string", "null"], "maxLength": 160},
        "clarification_question": {"type": ["string", "null"], "maxLength": 200},
        "clarification_options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "minLength": 1, "maxLength": 60},
                    "message_role": {"type": "string", "enum": sorted(CLARIFICATION_OPTION_ROLES)},
                    "resolved_message": {"type": "string", "minLength": 1, "maxLength": 500},
                },
                "required": ["label", "message_role", "resolved_message"],
                "additionalProperties": False,
            },
            "maxItems": 3,
        },
        "retrieval_query": {"type": "string", "minLength": 1, "maxLength": 300},  # Standalone DB search wording.
        "retrieval_subqueries": {
            "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 300},  # Compound question parts.
            "maxItems": 3,  # Limit model-suggested searches per turn.
        },
        "operational_request": {"type": "string", "enum": sorted(OPERATIONAL_REQUESTS)},  # Course/application lookup.
    },
    # Requiring all fields makes missing model judgments a validation error
    # instead of allowing an accidental default route or score.
    "required": [
        "message_role", "target_concepts", "missing_context",
        "clarification_question", "clarification_options",
        "retrieval_query", "retrieval_subqueries", "operational_request",
    ],
    "additionalProperties": False,  # Reject unrecognized model-created fields.
}

# Rule-based fallbacks below detect explicit wording when the classifier model
# is unavailable. They are not the complete intent-recognition system.
ADMIN_PATTERN = re.compile(
    r"\b(?:assignment|rubric|deadline|due date|submission|submit|points?|grade|"
    r"office hours?|schedule|syllabus|uploaded files?)\b",
    re.IGNORECASE,
)
# Anchor at both ends so a sentence mentioning "stop" is not mistaken for
# a command to end the lesson.
SESSION_CONTROL_PATTERN = re.compile(
    r"^(?:stop|pause|end|quit|exit)(?:\s+(?:the\s+)?(?:chat|lesson|session|questions?))?[.! ]*$",
    re.IGNORECASE,
)
HINT_PATTERN = re.compile(r"\b(?:hint|clue|nudge|help me start|guide me)\b", re.IGNORECASE)  # Explicit support request.
# An explicit preference for a direct response can override discovery mode.
DIRECT_ANSWER_PATTERN = re.compile(
    r"\b(?:just tell me|give me the answer|answer directly|no questions?|stop asking)\b", re.IGNORECASE,
)
# Asking "is that correct?" differs from merely answering the tutor.
CONFIRMATION_REQUEST_PATTERN = re.compile(
    r"(?:\b(?:is that|am i|is this|would that be|does that mean)\s+(?:right|correct|accurate)\b|"
    r"\b(?:right|correct|accurate)\s*\?)",
    re.IGNORECASE,
)
# Self-reported confusion raises support; it is not graded as an answer.
UNCERTAIN_PATTERN = re.compile(
    r"\b(?:i (?:still )?(?:do not|don't) know|not sure|unsure|confused|no idea|stuck)\b", re.IGNORECASE,
)
TENTATIVE_ANSWER_PATTERN = re.compile(
    r"\b(?:perhaps|maybe|i (?:think|guess|suppose)|it (?:could|might) be)\b", re.IGNORECASE,
)
# Tentative contradictory phrasing is a cue to check a claim against evidence.
MISCONCEPTION_PATTERN = re.compile(
    r"\b(?:i thought|isn't it|is it not|but i think|shouldn't|cannot be|can't be)\b", re.IGNORECASE,
)
REASONING_PATTERN = re.compile(r"\b(?:because|therefore|since|which means|so that)\b", re.IGNORECASE)  # Possible reasoning.
# These openings commonly introduce a new concept rather than answer a prompt.
DEFINITION_REQUEST_PATTERN = re.compile(
    r"^(?:what (?:is|are)|define|explain|tell me about|help me understand)\b", re.IGNORECASE,
)
# The next two patterns work together: asking what a phrase means, plus a
# pointer to earlier tutor wording, should stay in the existing topic.
CONTEXTUAL_MEANING_PATTERN = re.compile(
    r"^(?:what|how|can you|could you|explain)\b.*\b(?:mean|means|meaning|refer(?:s)? to)\b",
    re.IGNORECASE,
)
CONTEXT_REFERENCE_PATTERN = re.compile(
    r'["“”]|\b(?:in (?:this|the) context|here|that phrase|this phrase|your (?:last|previous) (?:question|message))\b',
    re.IGNORECASE,
)
# A learner can also identify the referent by explicitly asking the tutor to
# restate its immediately preceding question. This is not missing context: the
# tutor already owns the wording that needs to be simplified.
QUESTION_REPHRASE_PATTERN = re.compile(
    r"(?:\b(?:did not|didn't|do not|don't)\s+(?:get|understand)\s+(?:your|the|that)\s+question\b|"
    r"\b(?:make|say)\s+(?:it|your question|the question|that question)\s+"
    r"(?:a bit\s+|more\s+)?(?:clearer|simpler|clearly|simply)\b|"
    r"\brephrase\s+(?:it|your question|the question|that question)\b|"
    r"\bwhat\s+(?:are|were)\s+you\s+asking\b)",
    re.IGNORECASE,
)
UNKNOWN_TERM_PATTERN = re.compile(
    r"^\s*i\s+(?:do not|don't)\s+(?:know|understand)\s+what\s+(?:the\s+)?"
    r"(?P<term>[A-Za-z][A-Za-z0-9_.-]{1,30})\s+(?:is|means)\s*[?.!]*\s*$",
    re.IGNORECASE,
)
ACRONYM_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{2,9}\b")


def _one_typo_apart(left: str, right: str) -> bool:
    """Recognize one substitution, insertion/deletion, or adjacent transposition."""
    left, right = left.upper(), right.upper()
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [index for index, pair in enumerate(zip(left, right, strict=True)) if pair[0] != pair[1]]
        return len(differences) == 1 or (
            len(differences) == 2
            and differences[1] == differences[0] + 1
            and left[differences[0]] == right[differences[1]]
            and left[differences[1]] == right[differences[0]]
        )
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    return any(longer[:index] + longer[index + 1:] == shorter for index in range(len(longer)))


def recent_term_correction(message: str, history: list[ChatMessage]) -> tuple[str, str] | None:
    """Resolve a likely acronym typo against terms already used in this conversation."""
    match = UNKNOWN_TERM_PATTERN.match(message)
    if not match:
        return None
    learner_term = match.group("term")
    if not learner_term.isupper() or len(learner_term) < 3:
        return None
    for item in reversed(history):
        if item.role != "assistant":
            continue
        for candidate in reversed(ACRONYM_PATTERN.findall(item.content)):
            if candidate != learner_term and _one_typo_apart(learner_term, candidate):
                return learner_term, candidate
    return None


def is_contextual_meaning_request(message: str, history: list[ChatMessage]) -> bool:
    """A learner is asking about wording the tutor just used, not opening a new topic."""
    unknown_term = UNKNOWN_TERM_PATTERN.match(message)
    recent_assistant_text = "\n".join(item.content for item in history[-8:] if item.role == "assistant")
    return bool(
        (
            CONTEXTUAL_MEANING_PATTERN.search(message)
            and CONTEXT_REFERENCE_PATTERN.search(message)
            or QUESTION_REPHRASE_PATTERN.search(message)
            or (
                unknown_term
                and re.search(
                    rf"\b{re.escape(unknown_term.group('term'))}\b",
                    recent_assistant_text,
                    re.IGNORECASE,
                )
            )
        )
        and bool(recent_assistant_text)
    )


@dataclass(frozen=True)
class MessageClassification:
    """Validated interpretation used to route retrieval and Socratic teaching."""

    message_role: str = "learning_question"  # Single model observation; Python derives controller fields below.
    route: str = "learning"  # Which broad pipeline handles this message.
    target_concepts: tuple[str, ...] = ()  # Named topics to keep retrieval focused.
    dialogue_status: str = "new_topic"  # Status used by answer-evaluation eligibility.
    conversation_action: str = "continue"  # Immediate action for the chat controller.
    has_substantive_claim: bool = False  # Whether there is a proposition to assess.
    wants_to_continue: bool = True  # False for a closing or near-closing.
    confidence: float = 0.0  # Confidence in classification, not student mastery.
    needs_clarification: bool = False  # True when the target is too ambiguous.
    clarification_question: str | None = None  # One question for the missing context.
    clarification_options: tuple[ClarificationOption, ...] = ()  # Clickable meanings for a genuinely ambiguous turn.
    target: str | None = None  # Primary concept used by downstream evaluation.
    direct_answer: str | None = None  # Deterministic reply for a guarded special case.
    rewritten_query: str | None = None  # Standalone wording for database retrieval.
    retrieval_subqueries: tuple[str, ...] = ()  # Extra searches for compound questions.
    operational_request: str = "none"  # Course/application metadata lookup, if any.
    understanding_level: str = "unknown"  # Legacy DB field; the pre-retrieval classifier no longer estimates mastery.
    source: str = "rules"  # Whether labels came from rules or the model.

    question_type: str = "unclear"  # Legacy route compatibility only.
    conversation_state: str = "new_concept"  # Legacy route compatibility only.
    support_level: int = 0  # No hint-level selection in the imported pipeline.
    student_claim: str | None = None  # Raw student text is evaluated directly.
    keyword_scope_match: bool | None = None  # Independent of message role and mastery; scoped assignments only.

    @property
    def assessment_candidate(self) -> bool:
        """Whether this observation may become grounded learning evidence later."""
        return bool(
            self.has_substantive_claim
            and self.dialogue_status in {"answering_tutor", "requesting_confirmation"}
            and self.conversation_action == "continue"
        )


ROLE_POLICY: dict[str, tuple[str, str, str, bool]] = {
    # role: (route, dialogue_status, action, wants_to_continue)
    "learning_question": ("learning", "new_topic", "continue", True),
    "student_answer": ("learning", "answering_tutor", "continue", True),
    "support_request": ("learning", "requesting_support", "continue", True),
    "direct_answer_request": ("learning", "requesting_support", "direct", True),
    "follow_up": ("learning", "requesting_support", "continue", True),
    "confirmation_request": ("learning", "requesting_confirmation", "continue", True),
    "understanding_claim": ("learning", "claiming_understanding", "verify_understanding", True),
    "acknowledgement": ("learning", "acknowledgement", "soft_close", False),
    "closing": ("session_control", "closing", "complete", False),
    "topic_change": ("learning", "changing_topic", "continue", True),
    "administrative": ("administrative", "administrative_request", "direct", True),
    "ambiguous": ("unclear", "unclear", "clarify", True),
}


def _classification_from_observation(
    *,
    message_role: str,
    concepts: tuple[str, ...] = (),
    missing_context: str | None = None,
    clarification_question: str | None = None,
    clarification_options: tuple[ClarificationOption, ...] = (),
    rewritten_query: str | None = None,
    retrieval_subqueries: tuple[str, ...] = (),
    operational_request: str = "none",
    confidence: float = 0.8,
    source: str = "llm",
) -> MessageClassification:
    """Turn one semantic observation into one internally consistent policy decision."""
    role = message_role if message_role in MESSAGE_ROLES else "ambiguous"
    route, dialogue_status, action, wants_to_continue = ROLE_POLICY[role]
    clarification = None
    if role == "ambiguous":
        supplied_question = " ".join(clarification_question.split())[:200] if clarification_question else None
        if supplied_question:
            clarification = supplied_question.rstrip(" ")
            if not clarification.endswith("?"):
                clarification += "?"
        else:
            detail = " ".join(missing_context.split())[:160] if missing_context else "the course concept or problem"
            if re.match(r"^(?:what|which|who|where|when|why|how|can|could|would|do|does|did|is|are)\b", detail, re.I):
                clarification = detail.rstrip("?.! ") + "?"
            else:
                clarification = f"What do you mean by {detail.rstrip('?.! ')}?"
    else:
        clarification_options = ()
    return MessageClassification(
        message_role=role,
        route=route,
        target_concepts=concepts,
        dialogue_status=dialogue_status,
        conversation_action=action,
        # The evaluator receives the original message, so its eligibility is
        # derived from the role instead of an LLM-created paraphrase.
        has_substantive_claim=role in {"student_answer", "confirmation_request"},
        wants_to_continue=wants_to_continue,
        confidence=confidence,
        needs_clarification=role == "ambiguous",
        clarification_question=clarification,
        clarification_options=clarification_options if role == "ambiguous" else (),
        target=concepts[0] if concepts else None,
        rewritten_query=rewritten_query,
        retrieval_subqueries=retrieval_subqueries,
        operational_request=operational_request,
        understanding_level="unknown",
        source=source,
    )


def _clean_concept(value: object) -> str | None:
    # Reject non-text model output before using a label as a retrieval target.
    if not isinstance(value, str):
        return None
    # Normalize whitespace/punctuation and remove articles or trailing verbs
    # so "the code review?" and "code review" share one concept label.
    concept = " ".join(value.strip(" \t\n\r?.!,;:'\"/").split())
    concept = re.sub(r"^(?:the|a|an)\s+", "", concept, flags=re.IGNORECASE)
    concept = re.sub(r"\s+(?:is|are)$", "", concept, flags=re.IGNORECASE)
    # Pronouns alone are not stable concepts; use conversation history instead.
    if not concept or concept.lower() in {"it", "this", "that", "these", "those", "they"} or len(concept) > 100:
        return None
    return concept


def _extract_concepts(message: str) -> tuple[str, ...]:
    # Rules identify obvious concepts even if the LLM classifier is offline.
    normalized = " ".join(message.strip().rstrip("?.!").split())
    # A comparison needs both named concepts rather than a single vague label.
    comparison_patterns = [
        r"\b(?:difference between|compare)\s+(.+?)\s+(?:and|with|to)\s+(.+)$",
        r"^how\s+(?:is|are)\s+(.+?)\s+and\s+(.+?)\s+different$",
        r"^how\s+(?:is|are)\s+(.+?)\s+different\s+from\s+(.+)$",
    ]
    for pattern in comparison_patterns:
        comparison = re.search(pattern, normalized, re.IGNORECASE)
        if comparison:
            values = (_clean_concept(comparison.group(1)), _clean_concept(comparison.group(2)))
            return tuple(value for value in values if value)

    # For a definition or process question, capture its subject after the
    # opening phrase (for example, "what is code review?").
    patterns = [
        r"^(?:please\s+)?(?:what (?:is|are)|define|explain(?:\s+what)?|tell me about|help me understand)\s+(.+)$",
        r"^(?:please\s+)?(?:why|how)\s+(?:does|do|is|are|can|could|would|should)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        candidate = re.split(
            r"\s+(?:work|important|useful|different|matter|affect|help|used)\b",
            match.group(1), maxsplit=1, flags=re.IGNORECASE,
        )[0]
        concept = _clean_concept(candidate)
        if concept:
            return (concept,)
    return ()


def _latest_concepts(history: list[ChatMessage]) -> tuple[str, ...]:
    # A short follow-up such as "why does it matter?" inherits the last topic.
    for item in reversed(history[-8:]):
        if item.role == "user":
            concepts = _extract_concepts(item.content)
            if concepts:
                return concepts
    return ()


def _retrieval_query(message: str, concepts: tuple[str, ...]) -> str:
    # Add any inferred concept missing from the literal message so retrieval
    # can search for the intended subject, not only a pronoun or short reply.
    clean = " ".join(message.strip().split())
    missing = [concept for concept in concepts if concept.lower() not in clean.lower()]
    return " ".join([clean, *missing]).strip()


def _rule_classification(message: str, history: list[ChatMessage]) -> MessageClassification:
    # This deterministic interpretation is the offline safety net.  It emits
    # the same single observation used by the model-backed path, then applies
    # the shared policy mapper instead of constructing controller labels one by one.
    clean = " ".join(message.strip().split())
    lowered = clean.lower()
    concepts = _extract_concepts(clean)

    if SESSION_CONTROL_PATTERN.match(clean):
        return _classification_from_observation(
            message_role="closing", confidence=1.0, source="rules",
        )

    if ADMIN_PATTERN.search(clean):
        return _classification_from_observation(
            message_role="administrative", concepts=concepts,
            rewritten_query=clean,
            confidence=0.98, source="rules",
        )

    has_recent_tutor = bool(history and any(item.role == "assistant" for item in history[-2:]))
    if QUESTION_REPHRASE_PATTERN.search(clean) and has_recent_tutor:
        role = "support_request"
    elif HINT_PATTERN.search(clean) or UNCERTAIN_PATTERN.search(clean):
        role = "support_request"
    elif DIRECT_ANSWER_PATTERN.search(clean):
        role = "direct_answer_request"
    elif CONFIRMATION_REQUEST_PATTERN.search(clean):
        role = "confirmation_request"
    elif re.fullmatch(r"(?:i understand(?: it)?|i get it|got it)[.! ]*", lowered):
        role = "understanding_claim"
    elif re.fullmatch(r"(?:ok(?:ay)?|thanks?|thank you|sounds good)[.! ]*", lowered):
        role = "acknowledgement"
    elif has_recent_tutor and not clean.endswith("?"):
        role = "student_answer"
    elif has_recent_tutor and (CONTEXTUAL_MEANING_PATTERN.search(clean) or re.search(r"\b(?:it|this|that)\b", clean, re.I)):
        role = "follow_up"
    else:
        role = "learning_question"

    pronoun_follow_up = bool(re.search(r"\b(?:it|this|that|these|those|they)\b", clean, re.IGNORECASE))
    if not concepts and (clean.endswith("?") or role != "learning_question" or pronoun_follow_up):
        concepts = _latest_concepts(history)
        if concepts and pronoun_follow_up and role == "learning_question":
            role = "follow_up"

    vague = len(clean.split()) <= 2 and not concepts and role not in {
        "support_request", "direct_answer_request", "acknowledgement", "understanding_claim",
    }
    if vague:
        role = "ambiguous"
    return _classification_from_observation(
        message_role=role,
        concepts=concepts,
        missing_context="the course concept or problem" if vague else None,
        rewritten_query=_retrieval_query(clean, concepts),
        confidence=0.45 if vague else 0.72,
        source="rules",
    )


def _json_object(text: str) -> dict[str, Any]:
    # Accept a JSON object even if the provider wraps it in a code fence, but
    # reject prose or a JSON array before any routing fields are used.
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Classifier response must be a JSON object.")
    return value


def _validated_clarification_options(payload: dict[str, Any]) -> tuple[ClarificationOption, ...]:
    """Accept a small set of distinct, plain-language meanings from the model."""
    raw_options = payload.get("clarification_options")
    if not isinstance(raw_options, list):
        return ()
    options: list[ClarificationOption] = []
    seen_labels: set[str] = set()
    for item in raw_options[:3]:
        if not isinstance(item, dict):
            continue
        role = item.get("message_role")
        raw_label = item.get("label")
        raw_resolved = item.get("resolved_message")
        if role not in CLARIFICATION_OPTION_ROLES or not isinstance(raw_label, str) or not isinstance(raw_resolved, str):
            continue
        label = " ".join(raw_label.split())[:60]
        resolved = " ".join(raw_resolved.split())[:500]
        if not label or not resolved or label.casefold() in seen_labels:
            continue
        seen_labels.add(label.casefold())
        options.append(ClarificationOption(label=label, message_role=role, resolved_message=resolved))

    # Two plausible meanings are required before the UI interrupts the lesson.
    if len(options) < 2:
        return ()
    # Always leave the learner a low-pressure way to say neither interpretation
    # is clear. This selection requests support and never becomes mastery evidence.
    if len(options) < 3 and not any(option.message_role == "support_request" for option in options):
        options.append(ClarificationOption(
            label="I'm still not sure",
            message_role="support_request",
            resolved_message="I am still unsure and need a simpler explanation of the current question.",
        ))
    return tuple(options[:3])


def _validated_llm_classification(
    payload: dict[str, Any], message: str, fallback: MessageClassification,
) -> MessageClassification:
    # The live schema supplies one semantic role.  The legacy-field mapping is
    # retained only so old saved traces and focused unit fixtures remain
    # inspectable; none of those old controller labels is trusted directly.
    role = payload.get("message_role")
    if role not in MESSAGE_ROLES:
        state = payload.get("conversation_state")
        dialogue = payload.get("dialogue_status")
        route = payload.get("route")
        if state == "closing" or dialogue == "closing":
            role = "closing"
        elif state == "changing_topic" or dialogue == "changing_topic":
            role = "topic_change"
        elif route == "administrative" or dialogue == "administrative_request":
            role = "administrative"
        elif state in {"requesting_hint", "uncertain"} or dialogue in {"requesting_support", "uncertain"}:
            role = "support_request"
        elif state == "requesting_answer":
            role = "direct_answer_request"
        elif state == "claiming_understanding" or dialogue == "claiming_understanding":
            role = "understanding_claim"
        elif state == "acknowledging" or dialogue == "acknowledgement":
            role = "acknowledgement"
        elif dialogue == "requesting_confirmation":
            role = "confirmation_request"
        elif state in {"answering_tutor", "reasoning_in_progress", "possible_misconception"} or dialogue in {
            "answering_tutor", "reasoning_in_progress",
        }:
            role = "student_answer"
        elif state == "follow_up":
            role = "follow_up"
        elif route == "unclear" or payload.get("needs_clarification") is True:
            role = "ambiguous"
        elif state == "new_concept":
            role = "learning_question"
        else:
            role = fallback.message_role

    operational_request = (
        payload.get("operational_request")
        if payload.get("operational_request") in OPERATIONAL_REQUESTS
        else fallback.operational_request
    )
    raw_concepts = payload.get("target_concepts")
    concepts: tuple[str, ...] = ()
    if isinstance(raw_concepts, list):
        cleaned_concepts = [concept for concept in (_clean_concept(item) for item in raw_concepts) if concept]
        concepts = tuple(dict.fromkeys(cleaned_concepts))
    concepts = concepts or fallback.target_concepts

    # Explicit wording remains a deterministic boundary.  These guards do not
    # decide course meaning; they prevent a model role from bypassing the
    # student's clear request.
    if DEFINITION_REQUEST_PATTERN.match(message) and operational_request == "none":
        if role in {"administrative", "support_request", "direct_answer_request"}:
            role = fallback.message_role
        concepts = fallback.target_concepts
    if DIRECT_ANSWER_PATTERN.search(message):
        role = "direct_answer_request"
    elif role == "direct_answer_request":
        role = fallback.message_role
    if role == "confirmation_request" and not CONFIRMATION_REQUEST_PATTERN.search(message):
        role = fallback.message_role

    rewrite = payload.get("retrieval_query")
    if not isinstance(rewrite, str) or not rewrite.strip() or len(rewrite) > 300:
        rewrite = _retrieval_query(message, concepts)
    rewrite = " ".join(rewrite.split())

    raw_subqueries = payload.get("retrieval_subqueries")
    subqueries: list[str] = []
    if isinstance(raw_subqueries, list):
        context_terms = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", f"{message} {rewrite}".lower())) - QUERY_STOP_WORDS
        for raw_subquery in raw_subqueries[:3]:
            if not isinstance(raw_subquery, str):
                continue
            subquery = " ".join(raw_subquery.split())
            subquery_terms = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", subquery.lower())) - QUERY_STOP_WORDS
            if (
                3 <= len(subquery) <= 300
                and subquery.lower() != rewrite.lower()
                and subquery.lower() not in {item.lower() for item in subqueries}
                and subquery_terms & context_terms
            ):
                subqueries.append(subquery)

    raw_missing = payload.get("missing_context")
    if not isinstance(raw_missing, str) or not raw_missing.strip():
        # Legacy traces used clarification_question; it is data describing the
        # missing referent, never a controller instruction.
        raw_missing = payload.get("clarification_question")
    missing_context = " ".join(raw_missing.split())[:160] if isinstance(raw_missing, str) and raw_missing.strip() else None
    raw_clarification_question = payload.get("clarification_question")
    clarification_question = (
        " ".join(raw_clarification_question.split())[:200]
        if isinstance(raw_clarification_question, str) and raw_clarification_question.strip()
        else None
    )
    clarification_options = _validated_clarification_options(payload) if role == "ambiguous" else ()

    return _classification_from_observation(
        message_role=role,
        concepts=concepts,
        missing_context=missing_context,
        clarification_question=clarification_question,
        clarification_options=clarification_options,
        rewritten_query=rewrite,
        retrieval_subqueries=tuple(subqueries),
        operational_request=operational_request,
        confidence=0.8,
        source="llm",
    )


def _client_config() -> tuple[str, str, str, str] | None:
    if not settings.CLASSIFIER_ENABLED:
        return None
    return settings.llm_client_config("classifier")


async def _classify_with_llm(
    message: str, history: list[ChatMessage], fallback: MessageClassification,
    learning_topic: str | None = None,
    allowed_keywords: tuple[str, ...] = (),
) -> MessageClassification:
    # The classifier asks the model for labels and a retrieval query, not for
    # the student-facing answer. If disabled, the rule-based result is used.
    config = _client_config()
    if config is None:
        return fallback
    provider, api_key, base_url, model = config
    # A bounded window gives pronouns and short replies context without
    # sending the entire transcript on every request.
    recent = history[-settings.CLASSIFIER_MAX_HISTORY :]
    conversation = "\n".join(f"{item.role}: {item.content}" for item in recent) or "(none)"
    system_prompt = (
        "Interpret a student's latest course-chat message. Do not answer it and do not choose a teaching action. "
        "Return one JSON object describing observable meaning only. Set message_role to exactly one of: "
        "learning_question (a course question), student_answer (an attempt to answer the tutor, whether right or "
        "wrong), support_request (asks for a hint, simpler wording, or says they are stuck), direct_answer_request "
        "(explicitly asks the tutor to answer), follow_up (asks about wording or an idea already in the exchange), "
        "confirmation_request (offers a claim and asks if it is correct), understanding_claim (says they understand "
        "without demonstrating it), acknowledgement, closing, topic_change, administrative, or ambiguous. "
        "Use ambiguous only when the recent conversation leaves at least two reasonable meanings that require different "
        "responses. A mixed message may be ambiguous when it contains both a tentative answer and a request for help. "
        "Return target_concepts as concise noun phrases inferred from the latest message and conversation, not a "
        "fixed topic list. Return missing_context as a short noun phrase only for ambiguous; "
        "otherwise null. For ambiguous, return one natural clarification_question and two or three short "
        "clarification_options. Each option must state a complete student-facing meaning, use one allowed message_role, "
        "and provide resolved_message as the standalone meaning to resume with. Include an 'I'm still not sure' "
        "support_request when space permits. Options clarify intent and must not reveal the course answer. For every "
        "non-ambiguous message, return clarification_question=null and clarification_options=[]. Return retrieval_query "
        "as one standalone search that resolves pronouns from history, plus "
        "zero to three retrieval_subqueries only for genuinely separate information needs. Return operational_request "
        "as none, list_documents, document_visibility, document_overview, course_title, course_instructor, "
        "course_scope, or system_status; use anything other than none only for an explicit application/course-metadata "
        "A declarative response to the tutor is student_answer even when incomplete, incorrect, or off target. "
        "A first question such as 'what is version control?' is learning_question. If the student asks what the "
        "previous tutor wording means, use follow_up; if they ask to make the previous question clearer, use "
        "support_request. Keep related subtopics inside the supplied original learning topic. Use topic_change only "
        "for an explicitly different primary learning objective. Never invent a concept, claim, or intention."
    )
    if allowed_keywords:
        system_prompt += keyword_scope_instruction(allowed_keywords) + (
            " Also return keyword_scope_match as a boolean. Use true for a question within those keywords, "
            "a contextual follow-up, an attempt to answer the tutor (even when wrong or off target), "
            "a support request about the current lesson, acknowledgement, closing, or platform metadata. "
            "Use false when the student asks to learn or explain an unrelated concept, even if it appears "
            "elsewhere in the document or the original objective description. For a mixed question, false "
            "if answering it would require teaching an unrelated concept. Do not conflate topic scope with "
            "correctness or understanding."
        )
    log_event(4, "classifier_llm_started", provider=provider, model=model)
    started = monotonic()
    response_format: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": "course_message_classification",
            "strict": True,
            "schema": CLASSIFICATION_SCHEMA,
        },
    }
    if allowed_keywords:
        response_format["json_schema"]["schema"] = {
            **CLASSIFICATION_SCHEMA,
            "properties": {**CLASSIFICATION_SCHEMA["properties"], "keyword_scope_match": {"type": "boolean"}},
            "required": [*CLASSIFICATION_SCHEMA["required"], "keyword_scope_match"],
        }
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Original learning topic: {learning_topic or '(not set yet)'}\n\n"
                f"Recent conversation:\n{conversation}\n\nLatest message:\n{message}"
            )},
        ],
        "temperature": settings.CLASSIFIER_TEMPERATURE,
        "response_format": response_format,
    }
    request.update(settings.completion_token_parameters(provider, settings.CLASSIFIER_MAX_TOKENS))
    write_llm_request_snapshot("classifier", provider, request)
    response = await chat_completion(api_key, base_url, request)
    raw = response.choices[0].message.content
    if not raw or not raw.strip():
        raise ValueError("Message classifier returned empty content.")
    latency_ms = round((monotonic() - started) * 1000)
    log_event(
        4, "classifier_llm_completed", provider=provider, model=model,
        latency_ms=latency_ms,
    )
    debug_preview("classifier_output", raw)
    payload = _json_object(raw)
    classification = _validated_llm_classification(payload, message, fallback)
    if allowed_keywords:
        if not isinstance(payload.get("keyword_scope_match"), bool):
            raise ValueError("Scoped classifier omitted its topic-scope observation.")
        classification = replace(classification, keyword_scope_match=payload["keyword_scope_match"])
    parsed_trace = {
        "model_observation": {
            "keyword_scope_match": classification.keyword_scope_match,
            "approved_keywords": list(allowed_keywords),
            "message_role": classification.message_role,
            "target_concepts": list(classification.target_concepts),
            "clarification_question": classification.clarification_question,
            "clarification_options": [option.model_dump(mode="json") for option in classification.clarification_options],
            "retrieval_query": classification.rewritten_query,
            "retrieval_subqueries": list(classification.retrieval_subqueries),
            "operational_request": classification.operational_request,
        },
        "python_policy": {
            "route": classification.route,
            "dialogue_status": classification.dialogue_status,
            "conversation_action": classification.conversation_action,
            "has_substantive_claim": classification.has_substantive_claim,
            "needs_clarification": classification.needs_clarification,
            "wants_to_continue": classification.wants_to_continue,
            "assessment_candidate": classification.assessment_candidate,
            "learning_evidence_source": "answer_evaluation_after_retrieval",
        },
    }
    update_llm_request_snapshot(
        "classifier",
        raw_response=raw,
        parsed_output=parsed_trace,
        latency_ms=latency_ms,
    )
    return classification


async def classify_message(
    message: str, history: list[ChatMessage], learning_topic: str | None = None,
    allowed_keywords: tuple[str, ...] = (),
) -> MessageClassification:
    """Apply hard routing guards, then use an LLM for educational interpretation.

    The LLM observes one message role, concepts, support need, and retrieval wording.
    It cannot override administrative or session-control rules, and malformed or
    unavailable model output falls back to deterministic behavior.
    """

    # Compute deterministic guards first. They remain available if the LLM
    # fails, returns malformed labels, or is not configured.
    fallback = _rule_classification(message, history)
    # Session commands are handled predictably; the model must not reinterpret
    # them as an ordinary topic question.
    if fallback.route == "session_control":
        return fallback
    try:
        result = await _classify_with_llm(message, history, fallback, learning_topic, allowed_keywords)
    except Exception as error:
        log_exception(4, "classifier_llm_failed", error, fallback="rules")
        return fallback

    # Preserve hard session-control boundaries after the model's output too.
    if SESSION_CONTROL_PATTERN.match(message.strip()):
        return fallback
    if fallback.route == "learning" and is_contextual_meaning_request(message, history):
        role = "support_request" if QUESTION_REPHRASE_PATTERN.search(message) else "follow_up"
        return replace(_classification_from_observation(
            message_role=role,
            concepts=result.target_concepts or fallback.target_concepts,
            rewritten_query=result.rewritten_query or fallback.rewritten_query,
            retrieval_subqueries=result.retrieval_subqueries,
            source=result.source,
        ), keyword_scope_match=result.keyword_scope_match)
    # Explicit surface evidence and the preceding tutor turn resolve the few
    # roles that must never be turned into a generic clarification.  This is a
    # normalization of the single observation, not a second intent system.
    protected_roles = {
        "support_request", "direct_answer_request", "confirmation_request",
        "understanding_claim", "acknowledgement",
    }
    normalized_role = result.message_role
    actionable_mixed_ambiguity = bool(
        result.message_role == "ambiguous"
        and len(result.clarification_options) >= 2
        and fallback.message_role == "support_request"
        and TENTATIVE_ANSWER_PATTERN.search(message)
    )
    if fallback.message_role in protected_roles and not actionable_mixed_ambiguity:
        normalized_role = fallback.message_role
    elif fallback.message_role == "student_answer" and result.message_role in {
        "ambiguous", "support_request", "confirmation_request", "learning_question", "follow_up",
    }:
        normalized_role = "student_answer"
    if normalized_role != result.message_role:
        return replace(_classification_from_observation(
            message_role=normalized_role,
            concepts=result.target_concepts or fallback.target_concepts,
            rewritten_query=result.rewritten_query or fallback.rewritten_query,
            retrieval_subqueries=result.retrieval_subqueries,
            operational_request=result.operational_request,
            source=result.source,
        ), keyword_scope_match=result.keyword_scope_match)
    return result
