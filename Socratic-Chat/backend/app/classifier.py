from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any

from app import settings
from app.pipeline_logging import debug_preview, log_event, log_exception
from app.schemas import ChatMessage


ROUTES = {"learning", "administrative", "session_control", "unclear"}
INTENTS = {
    "definition", "explanation", "comparison", "procedure", "application", "debugging",
    "confirmation", "comprehension_claim", "acknowledgement", "close_session", "changing_topic",
    "hint", "direct_answer", "administrative", "reflection", "unclear",
}
OPERATIONAL_REQUESTS = {
    "none",
    "list_documents",
    "document_visibility",
    "document_overview",
    "course_title",
    "course_instructor",
    "course_scope",
    "system_status",
}
QUESTION_TYPES = {
    "what", "why", "how", "comparison", "application", "debugging", "statement", "follow_up", "unclear",
}
CONVERSATION_STATES = {
    "new_concept", "answering_tutor", "reasoning_in_progress", "uncertain", "possible_misconception",
    "requesting_hint", "requesting_answer", "claiming_understanding", "acknowledging", "closing",
    "changing_topic", "follow_up",
}
DIALOGUE_STATUSES = {
    "new_topic", "answering_tutor", "requesting_confirmation", "claiming_understanding",
    "reasoning_in_progress", "uncertain", "requesting_support", "acknowledgement", "closing",
    "changing_topic", "administrative_request", "unclear",
}
CONVERSATION_ACTIONS = {
    "continue", "verify_claim", "verify_understanding", "soft_close", "complete", "clarify", "direct",
}
UNDERSTANDING_LEVELS = {"unknown", "beginner", "developing", "proficient"}

CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": sorted(ROUTES)},
        "student_intent": {"type": "string", "enum": sorted(INTENTS)},
        "question_type": {"type": "string", "enum": sorted(QUESTION_TYPES)},
        "target_concepts": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 100},
        },
        "conversation_state": {"type": "string", "enum": sorted(CONVERSATION_STATES)},
        "dialogue_status": {"type": "string", "enum": sorted(DIALOGUE_STATUSES)},
        "conversation_action": {"type": "string", "enum": sorted(CONVERSATION_ACTIONS)},
        "has_substantive_claim": {"type": "boolean"},
        "student_claim": {"type": ["string", "null"], "maxLength": 500},
        "wants_to_continue": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"], "maxLength": 200},
        "retrieval_query": {"type": "string", "minLength": 1, "maxLength": 300},
        "operational_request": {"type": "string", "enum": sorted(OPERATIONAL_REQUESTS)},
        "understanding_level": {"type": "string", "enum": sorted(UNDERSTANDING_LEVELS)},
        "support_level": {"type": "integer", "minimum": 0, "maximum": 3},
    },
    "required": [
        "route", "student_intent", "question_type", "target_concepts", "conversation_state",
        "dialogue_status", "conversation_action", "has_substantive_claim", "student_claim",
        "wants_to_continue", "confidence", "needs_clarification", "clarification_question",
        "retrieval_query", "operational_request", "understanding_level", "support_level",
    ],
    "additionalProperties": False,
}

ADMIN_PATTERN = re.compile(
    r"\b(?:assignment|rubric|deadline|due date|submission|submit|points?|grade|"
    r"office hours?|schedule|syllabus|uploaded files?)\b",
    re.IGNORECASE,
)
SESSION_CONTROL_PATTERN = re.compile(
    r"^(?:stop|pause|end|quit|exit)(?:\s+(?:the\s+)?(?:chat|lesson|session|questions?))?[.! ]*$",
    re.IGNORECASE,
)
HINT_PATTERN = re.compile(r"\b(?:hint|clue|nudge|help me start|guide me)\b", re.IGNORECASE)
DIRECT_ANSWER_PATTERN = re.compile(
    r"\b(?:just tell me|give me the answer|answer directly|no questions?|stop asking)\b", re.IGNORECASE,
)
UNCERTAIN_PATTERN = re.compile(
    r"\b(?:i (?:still )?(?:do not|don't) know|not sure|unsure|confused|no idea|stuck)\b", re.IGNORECASE,
)
MISCONCEPTION_PATTERN = re.compile(
    r"\b(?:i thought|isn't it|is it not|but i think|shouldn't|cannot be|can't be)\b", re.IGNORECASE,
)
REASONING_PATTERN = re.compile(r"\b(?:because|therefore|since|which means|so that)\b", re.IGNORECASE)


@dataclass(frozen=True)
class MessageClassification:
    """Validated interpretation used to route retrieval and Socratic teaching."""

    route: str = "learning"
    student_intent: str = "unclear"
    question_type: str = "unclear"
    target_concepts: tuple[str, ...] = ()
    conversation_state: str = "new_concept"
    dialogue_status: str = "new_topic"
    conversation_action: str = "continue"
    has_substantive_claim: bool = False
    student_claim: str | None = None
    wants_to_continue: bool = True
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: str | None = None
    target: str | None = None
    direct_answer: str | None = None
    rewritten_query: str | None = None
    operational_request: str = "none"
    understanding_level: str = "unknown"
    support_level: int = 0
    source: str = "rules"


def _clean_concept(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    concept = " ".join(value.strip(" \t\n\r?.!,;:'\"").split())
    concept = re.sub(r"^(?:the|a|an)\s+", "", concept, flags=re.IGNORECASE)
    concept = re.sub(r"\s+(?:is|are)$", "", concept, flags=re.IGNORECASE)
    if not concept or concept.lower() in {"it", "this", "that", "these", "those", "they"} or len(concept) > 100:
        return None
    return concept


def _extract_concepts(message: str) -> tuple[str, ...]:
    normalized = " ".join(message.strip().rstrip("?.!").split())
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
    for item in reversed(history[-8:]):
        if item.role == "user":
            concepts = _extract_concepts(item.content)
            if concepts:
                return concepts
    return ()


def _retrieval_query(message: str, concepts: tuple[str, ...]) -> str:
    clean = " ".join(message.strip().split())
    missing = [concept for concept in concepts if concept.lower() not in clean.lower()]
    return " ".join([clean, *missing]).strip()


def _rule_classification(message: str, history: list[ChatMessage]) -> MessageClassification:
    clean = " ".join(message.strip().split())
    lowered = clean.lower()
    concepts = _extract_concepts(clean)

    if SESSION_CONTROL_PATTERN.match(clean):
        return MessageClassification(
            route="session_control", student_intent="close_session", question_type="statement",
            conversation_state="closing", dialogue_status="closing", conversation_action="complete",
            wants_to_continue=False, confidence=1.0,
        )

    if ADMIN_PATTERN.search(clean):
        return MessageClassification(
            route="administrative", student_intent="administrative",
            question_type="what" if lowered.startswith("what") else "how",
            dialogue_status="administrative_request", conversation_action="direct",
            target_concepts=concepts, target=concepts[0] if concepts else None,
            confidence=0.98, rewritten_query=clean,
        )

    if HINT_PATTERN.search(clean):
        intent, state, dialogue_status, action = "hint", "requesting_hint", "requesting_support", "continue"
    elif DIRECT_ANSWER_PATTERN.search(clean):
        intent, state, dialogue_status, action = "direct_answer", "requesting_answer", "answering_tutor", "direct"
    elif UNCERTAIN_PATTERN.search(clean):
        intent, state, dialogue_status, action = "hint", "uncertain", "uncertain", "continue"
    elif MISCONCEPTION_PATTERN.search(clean):
        intent, state, dialogue_status, action = (
            "confirmation", "possible_misconception", "requesting_confirmation", "verify_claim"
        )
    elif REASONING_PATTERN.search(clean):
        intent, state, dialogue_status, action = (
            "explanation", "reasoning_in_progress", "reasoning_in_progress", "continue"
        )
    elif re.search(r"\b(?:difference between|compare|different|differ)\b", clean, re.IGNORECASE):
        intent, state, dialogue_status, action = "comparison", "new_concept", "new_topic", "continue"
    elif lowered.startswith("why"):
        intent, state, dialogue_status, action = "explanation", "new_concept", "new_topic", "continue"
    elif lowered.startswith("how"):
        intent, state, dialogue_status, action = "procedure", "new_concept", "new_topic", "continue"
    elif re.match(r"^(?:what (?:is|are)|define|explain|tell me about|help me understand)\b", lowered):
        intent, state, dialogue_status, action = "definition", "new_concept", "new_topic", "continue"
    else:
        intent = "confirmation" if clean.endswith("?") else "reflection"
        state = "answering_tutor" if history and any(item.role == "assistant" for item in history[-2:]) else "follow_up"
        dialogue_status = "answering_tutor" if state == "answering_tutor" else "unclear"
        action = "continue"

    if lowered.startswith("why"):
        question_type = "why"
    elif re.search(r"\b(?:difference between|compare|different|differ)\b", clean, re.IGNORECASE):
        question_type = "comparison"
    elif lowered.startswith("how"):
        question_type = "how"
    elif lowered.startswith("what") or intent == "definition":
        question_type = "what"
    elif clean.endswith("?"):
        question_type = "follow_up"
    else:
        question_type = "statement"

    pronoun_follow_up = bool(re.search(r"\b(?:it|this|that|these|those|they)\b", clean, re.IGNORECASE))
    if not concepts and (question_type == "follow_up" or state != "new_concept" or pronoun_follow_up):
        concepts = _latest_concepts(history)
        if concepts and pronoun_follow_up:
            state = "follow_up"

    vague = len(clean.split()) <= 2 and not concepts and intent not in {"hint", "direct_answer"}
    return MessageClassification(
        route="unclear" if vague else "learning",
        student_intent="unclear" if vague else intent,
        question_type="unclear" if vague else question_type,
        target_concepts=concepts,
        conversation_state=state,
        dialogue_status="unclear" if vague else dialogue_status,
        conversation_action="clarify" if vague else action,
        confidence=0.45 if vague else 0.72,
        needs_clarification=vague,
        clarification_question="Which course concept or problem would you like to examine?" if vague else None,
        target=concepts[0] if concepts else None,
        rewritten_query=_retrieval_query(clean, concepts),
    )


def _json_object(text: str) -> dict[str, Any]:
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


def _validated_llm_classification(
    payload: dict[str, Any], message: str, fallback: MessageClassification,
) -> MessageClassification:
    route = payload.get("route") if payload.get("route") in ROUTES else fallback.route
    intent = payload.get("student_intent") if payload.get("student_intent") in INTENTS else fallback.student_intent
    question_type = payload.get("question_type") if payload.get("question_type") in QUESTION_TYPES else fallback.question_type
    state = payload.get("conversation_state") if payload.get("conversation_state") in CONVERSATION_STATES else fallback.conversation_state
    dialogue_status = (
        payload.get("dialogue_status")
        if payload.get("dialogue_status") in DIALOGUE_STATUSES
        else fallback.dialogue_status
    )
    action = (
        payload.get("conversation_action")
        if payload.get("conversation_action") in CONVERSATION_ACTIONS
        else fallback.conversation_action
    )
    operational_request = (
        payload.get("operational_request")
        if payload.get("operational_request") in OPERATIONAL_REQUESTS
        else fallback.operational_request
    )
    understanding_level = (
        payload.get("understanding_level")
        if payload.get("understanding_level") in UNDERSTANDING_LEVELS
        else fallback.understanding_level
    )
    try:
        support_level = min(3, max(0, int(payload.get("support_level", fallback.support_level))))
    except (TypeError, ValueError):
        support_level = fallback.support_level
    raw_concepts = payload.get("target_concepts")
    concepts: tuple[str, ...] = ()
    if isinstance(raw_concepts, list):
        concepts = tuple(concept for concept in (_clean_concept(item) for item in raw_concepts[:3]) if concept)
    concepts = concepts or fallback.target_concepts
    try:
        confidence = min(1.0, max(0.0, float(payload.get("confidence", fallback.confidence))))
    except (TypeError, ValueError):
        confidence = fallback.confidence
    needs_clarification = bool(payload.get("needs_clarification", False)) and confidence < 0.75
    clarification = _clean_concept(payload.get("clarification_question")) if needs_clarification else None
    if needs_clarification and not clarification:
        clarification = "Which course concept or problem would you like to examine?"
    rewrite = payload.get("retrieval_query")
    if not isinstance(rewrite, str) or not rewrite.strip() or len(rewrite) > 300:
        rewrite = _retrieval_query(message, concepts)
    raw_claim = payload.get("student_claim")
    student_claim = " ".join(raw_claim.strip().split())[:500] if isinstance(raw_claim, str) and raw_claim.strip() else None
    has_substantive_claim = payload.get("has_substantive_claim") is True and student_claim is not None
    wants_to_continue = payload.get("wants_to_continue") is not False
    if action in {"soft_close", "complete"}:
        wants_to_continue = False
    if action == "complete" and (dialogue_status != "closing" or confidence < 0.8):
        action = "soft_close"
    if action == "verify_claim" and not has_substantive_claim:
        action = "clarify"
        needs_clarification = True
        clarification = "What specific understanding would you like me to check?"
    if action == "clarify":
        needs_clarification = True
        if not clarification:
            clarification = "Could you clarify what you want to explore or verify?"
    return MessageClassification(
        route=route, student_intent=intent, question_type=question_type,
        target_concepts=concepts, conversation_state=state, dialogue_status=dialogue_status,
        conversation_action=action, has_substantive_claim=has_substantive_claim,
        student_claim=student_claim, wants_to_continue=wants_to_continue, confidence=confidence,
        needs_clarification=needs_clarification, clarification_question=clarification,
        target=concepts[0] if concepts else None,
        rewritten_query=" ".join(rewrite.split()), operational_request=operational_request,
        understanding_level=understanding_level, support_level=support_level,
        source="llm",
    )


def _client_config() -> tuple[str, str, str, str] | None:
    if not settings.CLASSIFIER_ENABLED:
        return None
    if settings.OPENAI_API_KEY:
        return "OpenAI", settings.OPENAI_API_KEY, settings.OPENAI_API_BASE_URL, settings.CLASSIFIER_MODEL or settings.RAG_MODEL
    return None


async def _classify_with_llm(
    message: str, history: list[ChatMessage], fallback: MessageClassification,
) -> MessageClassification:
    from openai import AsyncOpenAI

    config = _client_config()
    if config is None:
        return fallback
    provider, api_key, base_url, model = config
    recent = history[-settings.CLASSIFIER_MAX_HISTORY :]
    conversation = "\n".join(f"{item.role}: {item.content}" for item in recent) or "(none)"
    system_prompt = (
        "Classify a student's latest course-chat message. Do not answer it. Return one JSON object only with: "
        "route (learning, administrative, session_control, unclear); student_intent (definition, explanation, "
        "comparison, procedure, application, debugging, confirmation, hint, direct_answer, administrative, "
        "comprehension_claim, acknowledgement, close_session, changing_topic, reflection, unclear); question_type "
        "(what, why, how, comparison, application, debugging, statement, "
        "follow_up, unclear); target_concepts (zero to three concise noun phrases); conversation_state "
        "(new_concept, answering_tutor, reasoning_in_progress, uncertain, possible_misconception, requesting_hint, "
        "requesting_answer, claiming_understanding, acknowledging, closing, changing_topic, follow_up); "
        "dialogue_status (new_topic, answering_tutor, requesting_confirmation, claiming_understanding, "
        "reasoning_in_progress, uncertain, requesting_support, acknowledgement, closing, changing_topic, "
        "administrative_request, unclear); conversation_action (continue, verify_claim, verify_understanding, "
        "soft_close, complete, clarify, direct); has_substantive_claim (boolean); student_claim (the student's "
        "actual proposition to verify or null); wants_to_continue (boolean); confidence (0 to 1); "
        "needs_clarification (boolean); clarification_question "
        "(one short question or null); retrieval_query (a concise standalone search query that preserves named "
        "course items and resolves pronouns from history); operational_request (none, list_documents, "
        "document_visibility, document_overview, course_title, course_instructor, course_scope, or system_status). "
        "Also return understanding_level (unknown, beginner, developing, or proficient) for the student's currently "
        "demonstrated understanding of the target concept, and support_level (0 to 3), where 0 means no additional "
        "support, 1 means a small scaffold, 2 means the student remains confused and needs a simpler different "
        "example plus a concise explanation, and 3 means repeated difficulty needs a step-by-step worked example. "
        "Infer these from the latest message and recent conversation; never equate confidence or fluent wording with "
        "subject mastery. The objective is learning and understanding the instructor-published topic. "
        "Use an operational request only when the student explicitly asks for that application or course metadata. "
        "Ordinary learning statements that merely mention files, documents, folders, seeing, or having something "
        "must remain operational_request=none. Distinguish a bare understanding claim from a claim "
        "that contains reasoning. Treat thanks without a question as acknowledgement/soft_close, a clear goodbye "
        "as closing/complete, and a claim asking whether it is correct as requesting_confirmation/verify_claim. "
        "Never invent a concept, claim, or intention absent from the message and recent history."
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Recent conversation:\n{conversation}\n\nLatest message:\n{message}"},
        ],
        "temperature": settings.CLASSIFIER_TEMPERATURE,
        "max_completion_tokens": settings.CLASSIFIER_MAX_TOKENS,
        "response_format": response_format,
    }
    response = await client.chat.completions.create(**request)
    raw = response.choices[0].message.content
    if not raw or not raw.strip():
        raise ValueError("Message classifier returned empty content.")
    log_event(
        4, "classifier_llm_completed", provider=provider, model=model,
        latency_ms=round((monotonic() - started) * 1000),
    )
    debug_preview("classifier_output", raw)
    return _validated_llm_classification(_json_object(raw), message, fallback)


async def classify_message(message: str, history: list[ChatMessage]) -> MessageClassification:
    """Apply hard routing guards, then use an LLM for educational interpretation.

    The LLM may improve intent, concept, follow-up, and retrieval-query detection.
    It cannot override administrative or session-control rules, and malformed or
    unavailable model output falls back to deterministic behavior.
    """

    fallback = _rule_classification(message, history)
    if fallback.route == "session_control":
        return fallback
    try:
        result = await _classify_with_llm(message, history, fallback)
    except Exception as error:
        log_exception(4, "classifier_llm_failed", error, fallback="rules")
        return fallback

    if SESSION_CONTROL_PATTERN.match(message.strip()):
        return fallback
    if result.route == "session_control":
        return replace(result, route=fallback.route, direct_answer=None)
    return result
