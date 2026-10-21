from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
import re
from time import monotonic
from typing import Any

from app import db, settings
from app.llm_client import chat_completion
from app.pipeline_logging import (
    log_event,
    log_exception,
    update_llm_request_snapshot,
    write_llm_request_snapshot,
)
from app.schemas import ChatMessage


TERM_PATTERNS = (
    re.compile(
        r"\bi\s+(?:do not|don't)\s+(?:know|understand)\s+what\s+(?:the\s+)?"
        r"(?P<term>[A-Za-z][A-Za-z0-9_.+-]{1,30})\s+(?:is|means)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what\s+(?:is|does)\s+(?:the\s+)?(?P<term>[A-Za-z][A-Za-z0-9_.+-]{1,30})"
        r"(?:\s+mean)?\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
)
TOKEN_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_.+-]{2,39}\b")

TERM_RESOLUTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["corrected", "unchanged", "ambiguous"]},
        "selected_term": {"type": ["string", "null"], "maxLength": 40},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 160},
    },
    "required": ["decision", "selected_term", "confidence", "reason"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class TermResolution:
    original_term: str
    selected_term: str
    confidence: float
    source: str
    candidates: tuple[str, ...]


def extract_definition_term(message: str) -> str | None:
    for pattern in TERM_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group("term")
    return None


def _damerau_levenshtein(left: str, right: str) -> int:
    """Small unrestricted-enough edit metric for misspellings and transpositions."""
    left, right = left.casefold(), right.casefold()
    rows = len(left) + 1
    columns = len(right) + 1
    distance = [[0] * columns for _ in range(rows)]
    for row in range(rows):
        distance[row][0] = row
    for column in range(columns):
        distance[0][column] = column
    for row in range(1, rows):
        for column in range(1, columns):
            cost = 0 if left[row - 1] == right[column - 1] else 1
            distance[row][column] = min(
                distance[row - 1][column] + 1,
                distance[row][column - 1] + 1,
                distance[row - 1][column - 1] + cost,
            )
            if (
                row > 1
                and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                distance[row][column] = min(distance[row][column], distance[row - 2][column - 2] + 1)
    return distance[-1][-1]


def candidate_terms(term: str, history: list[ChatMessage], document_terms: list[str]) -> tuple[str, ...]:
    """Rank close spellings from conversation and published-course vocabulary."""
    seen: set[str] = set()
    ranked: list[tuple[int, float, int, str]] = []
    history_terms: list[str] = []
    for item in reversed(history):
        if item.role == "assistant":
            history_terms.extend(reversed(TOKEN_PATTERN.findall(item.content)))
    for source_priority, candidate in [(0, item) for item in history_terms] + [
        (1, item) for item in document_terms
    ]:
        normalized = candidate.casefold()
        if normalized == term.casefold() or normalized in seen:
            continue
        seen.add(normalized)
        distance = _damerau_levenshtein(term, candidate)
        ratio = SequenceMatcher(None, term.casefold(), normalized).ratio()
        allowed_distance = 1 if max(len(term), len(candidate)) <= 5 else 2
        if distance <= allowed_distance and ratio >= 0.68:
            ranked.append((distance, -ratio, source_priority, candidate))
    ranked.sort()
    return tuple(item[3] for item in ranked[:8])


def _json_object(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Term resolver response must be a JSON object.")
    return value


def _single_verified_fallback(
    original: str,
    candidates: tuple[str, ...],
    document_terms: list[str],
    source: str,
) -> TermResolution | None:
    """Accept only one close candidate that actually exists in published material."""
    if len(candidates) != 1 or _damerau_levenshtein(original, candidates[0]) != 1:
        return None
    document_vocabulary = {term.casefold() for term in document_terms}
    selected = candidates[0]
    if selected.casefold() not in document_vocabulary:
        return None
    return TermResolution(original, selected, 0.85, source, candidates)


async def resolve_term(
    message: str,
    history: list[ChatMessage],
    course_id: str | None,
    conversation_id: str | None,
    document_terms: list[str] | None = None,
) -> TermResolution | None:
    """Let Qwen choose only among typo candidates verified against local context."""
    original = extract_definition_term(message)
    if not original:
        return None
    vocabulary = document_terms if document_terms is not None else db.published_document_terms(
        course_id=course_id, conversation_id=conversation_id,
    )
    candidates = candidate_terms(original, history, vocabulary)
    if not candidates:
        return None
    verified_fallback = _single_verified_fallback(
        original, candidates, vocabulary, "python_verified",
    )
    config = settings.llm_client_config("classifier") if settings.CLASSIFIER_ENABLED else None
    if config is None:
        return verified_fallback
    provider, api_key, base_url, model = config
    recent = "\n".join(f"{item.role}: {item.content}" for item in history[-6:]) or "(none)"
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Resolve a possible typo in a student's course term. Choose selected_term only from the supplied "
                    "verified candidates. Use corrected only when the conversation makes the intended term clear; use "
                    "ambiguous when multiple candidates remain plausible; otherwise use unchanged with null. Do not "
                    "answer the student's course question. Return one JSON object only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Student message: {message}\nOriginal term: {original}\n"
                    f"Verified candidates: {', '.join(candidates)}\nRecent conversation:\n{recent}"
                ),
            },
        ],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "course_term_resolution", "strict": True, "schema": TERM_RESOLUTION_SCHEMA},
        },
    }
    request.update(settings.completion_token_parameters(provider, 250))
    write_llm_request_snapshot("term-resolution", provider, request)
    started = monotonic()
    try:
        response = await chat_completion(api_key, base_url, request)
        raw = response.choices[0].message.content
        payload = _json_object(raw or "")
        decision = payload.get("decision")
        selected = payload.get("selected_term")
        confidence = float(payload.get("confidence", 0))
        if decision != "corrected" or selected not in candidates or confidence < 0.7:
            final_result = verified_fallback
            update_llm_request_snapshot(
                "term-resolution",
                raw_response=raw,
                parsed_output={
                    "original_term": original,
                    "candidates": list(candidates),
                    "decision": decision,
                    "selected_term": selected,
                    "confidence": confidence,
                    "verified_fallback": asdict(final_result) if final_result else None,
                },
                latency_ms=round((monotonic() - started) * 1000),
            )
            if final_result:
                log_event(
                    4,
                    "term_resolved",
                    original_term=original,
                    selected_term=final_result.selected_term,
                    confidence=final_result.confidence,
                    candidates=len(candidates),
                    source=final_result.source,
                )
            return final_result
        result = TermResolution(original, selected, confidence, "llm_verified", candidates)
        update_llm_request_snapshot(
            "term-resolution",
            raw_response=raw,
            parsed_output=asdict(result),
            latency_ms=round((monotonic() - started) * 1000),
        )
        log_event(
            4,
            "term_resolved",
            original_term=original,
            selected_term=selected,
            confidence=round(confidence, 2),
            candidates=len(candidates),
        )
        return result
    except Exception as error:
        log_exception(4, "term_resolution_failed", error, fallback="single_verified_candidate")
        if verified_fallback:
            return TermResolution(
                verified_fallback.original_term,
                verified_fallback.selected_term,
                verified_fallback.confidence,
                "python_verified_after_model_failure",
                verified_fallback.candidates,
            )
        return None
