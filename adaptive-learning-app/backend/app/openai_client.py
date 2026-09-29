from __future__ import annotations

import hashlib
import json
import math
import re

import httpx

from .config import (
    AI_MODE,
    ALLOW_DEMO_FALLBACK,
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENAI_API_KEY,
    OPENAI_CHAT_MODEL,
    OPENAI_EMBEDDING_MODEL,
)


OPENAI_BASE = "https://api.openai.com/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"
_runtime_fallback = False


def runtime_ai_mode() -> str:
    if AI_MODE == "demo":
        return "demo"
    if _runtime_fallback:
        return "demo-fallback"
    if AI_MODE == "groq":
        return "groq" if GROQ_API_KEY else "demo"
    return "openai" if OPENAI_API_KEY else "demo"


def _activate_fallback(error: Exception) -> bool:
    global _runtime_fallback
    if not ALLOW_DEMO_FALLBACK:
        return False
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code not in {401, 403, 404, 408, 429, 500, 502, 503, 504}:
        return False
    _runtime_fallback = True
    return True


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}


def _chat_settings() -> tuple[str, str, dict[str, str]]:
    if runtime_ai_mode() == "groq":
        return GROQ_BASE, GROQ_MODEL, {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
    return OPENAI_BASE, OPENAI_CHAT_MODEL, _headers()


def _demo_embedding(text: str, dimensions: int = 96) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not OPENAI_API_KEY:
        return [_demo_embedding(text) for text in texts]
    try:
        with httpx.Client(timeout=45) as client:
            response = client.post(
                f"{OPENAI_BASE}/embeddings",
                headers=_headers(),
                json={"model": OPENAI_EMBEDDING_MODEL, "input": texts},
            )
            response.raise_for_status()
            items = sorted(response.json()["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in items]
    except httpx.HTTPError as exc:
        if not _activate_fallback(exc):
            raise
        return [_demo_embedding(text) for text in texts]


def _is_llm_database_misconception(objective: dict, response: str) -> bool:
    objective_text = " ".join(
        [objective.get("title", ""), objective.get("description", "")]
    ).lower()
    response_text = response.lower()
    return (
        any(term in objective_text for term in ("large language model", "llm", "language model"))
        and "database" in response_text
        and not any(term in response_text for term in ("token", "predict", "probability", "pattern"))
    )


def _demo_assessment(response: str, criteria: list[str], objective: dict | None = None) -> dict:
    if objective and _is_llm_database_misconception(objective, response):
        return {
            "score": 0.1,
            "demonstrated": False,
            "rationale": (
                "This describes information retrieval rather than the normal text-generation "
                "process of a large language model."
            ),
        }
    words = set(re.findall(r"[a-z]+", response.lower()))
    substantive = len(words) >= 12
    reasoning = bool(words.intersection({"because", "therefore", "whereas", "measurable", "seconds", "functional", "quality"}))
    score = 0.45 + (0.3 if substantive else 0) + (0.25 if reasoning else 0)
    score = min(score, 1.0)
    return {
        "score": score,
        "demonstrated": score >= 0.7,
        "rationale": "The response includes a substantive explanation." if score >= 0.7 else "Add a clearer justification and connect it to the success criteria.",
    }


def assess_response(objective: dict, response: str) -> dict:
    if runtime_ai_mode() not in {"openai", "groq"}:
        return _demo_assessment(response, objective["success_criteria"], objective)
    chat_base, chat_model, chat_headers = _chat_settings()
    prompt = {
        "objective": objective["description"],
        "success_criteria": objective["success_criteria"],
        "student_response": response,
    }
    try:
        with httpx.Client(timeout=60) as client:
            result = client.post(
                f"{chat_base}/chat/completions",
                headers=chat_headers,
                json={
                    "model": chat_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "Assess the student response. Return JSON with score from 0 to 1, demonstrated boolean, and a concise rationale. Do not reveal a model answer."},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                },
            )
            result.raise_for_status()
            parsed = json.loads(result.json()["choices"][0]["message"]["content"])
            score = max(0.0, min(float(parsed.get("score", 0)), 1.0))
            return {
                "score": score,
                "demonstrated": bool(parsed.get("demonstrated", score >= 0.7)),
                "rationale": str(parsed.get("rationale", "Assessment completed."))[:1000],
            }
    except httpx.HTTPError as exc:
        if not _activate_fallback(exc):
            raise
        return _demo_assessment(response, objective["success_criteria"], objective)


def _demo_tutor_reply(
    objective: dict,
    student_response: str,
    assessment: dict,
    context: list[dict],
    next_prompt: str | None,
) -> str:
    if next_prompt:
        return f"Good work—you demonstrated this objective. Next, try this:\n\n{next_prompt}"
    if assessment["demonstrated"]:
        return "Good work—you demonstrated this objective with a specific, measurable explanation."
    if _is_llm_database_misconception(objective, student_response):
        return (
            "That describes a search or retrieval system, but a standard large language model "
            "normally generates text rather than looking up a complete answer in a database. "
            "Review the ideas of tokens, learned patterns, and next-token prediction in the "
            "course source. Then revise your answer and include a short example showing how a "
            "model predicts what comes next from context."
        )
    if context:
        excerpt = " ".join(context[0]["content"].split())
        hint = excerpt[:280].rsplit(" ", 1)[0]
        return (
            f"{assessment['rationale']} Here is a hint from {context[0]['filename']}: "
            f"“{hint}…” Revise your answer in your own words and include a concrete example."
        )
    return (
        f"{assessment['rationale']} Revise your answer with the central mechanism, "
        "a concrete example, and an explanation of why the example fits."
    )


def tutor_reply(objective: dict, student_response: str, assessment: dict, context: list[dict], next_prompt: str | None) -> str:
    if runtime_ai_mode() not in {"openai", "groq"}:
        return _demo_tutor_reply(objective, student_response, assessment, context, next_prompt)
    chat_base, chat_model, chat_headers = _chat_settings()
    sources = "\n\n".join(f"[{item['filename']}] {item['content']}" for item in context)
    instruction = (
        "You are an adaptive tutor. Give concise formative feedback without supplying the full answer. "
        "Use only the supplied course excerpts when making source-grounded claims. "
        "If a next prompt is supplied, acknowledge progress and ask that prompt."
    )
    payload = {
        "objective": objective,
        "student_response": student_response,
        "assessment": assessment,
        "course_excerpts": sources,
        "next_prompt": next_prompt,
    }
    try:
        with httpx.Client(timeout=60) as client:
            result = client.post(
                f"{chat_base}/chat/completions",
                headers=chat_headers,
                json={
                    "model": chat_model,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                },
            )
            result.raise_for_status()
            return result.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPError as exc:
        if not _activate_fallback(exc):
            raise
        return _demo_tutor_reply(objective, student_response, assessment, context, next_prompt)


def generate_learning_plan(topic: str, course_level: str) -> dict:
    """Generate a compact plan suitable for immediate assignment publication."""
    if runtime_ai_mode() not in {"openai", "groq"}:
        return _demo_learning_plan(topic, course_level)
    chat_base, chat_model, chat_headers = _chat_settings()

    request = {
        "topic": topic,
        "course_level": course_level,
        "requirements": {
            "objective_count": "2 to 4",
            "audience": "undergraduate students",
            "tone": "clear, rigorous, and accessible",
            "assessment": "diagnostic prompts must require explanation rather than recall",
            "required_task": "one authentic application or analysis task",
        },
        "json_shape": {
            "title": "string",
            "course_context": "string",
            "objectives": [
                {
                    "id": "SHORT-UPPERCASE-ID",
                    "title": "string",
                    "description": "string",
                    "success_criteria": ["string"],
                    "diagnostic_prompt": "string",
                }
            ],
            "required_task": {
                "title": "string",
                "description": "string",
                "submission_prompt": "string",
            },
        },
    }
    try:
        with httpx.Client(timeout=90) as client:
            result = client.post(
                f"{chat_base}/chat/completions",
                headers=chat_headers,
                json={
                    "model": chat_model,
                    "temperature": 0.25,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You design concise adaptive learning plans. Return only valid JSON matching the supplied shape. "
                                "Objectives must be distinct, measurable, and appropriate for the stated course level. "
                                "Do not ask the instructor for additional information."
                            ),
                        },
                        {"role": "user", "content": json.dumps(request)},
                    ],
                },
            )
            result.raise_for_status()
            return json.loads(result.json()["choices"][0]["message"]["content"])
    except httpx.HTTPError as exc:
        if not _activate_fallback(exc):
            raise
        return _demo_learning_plan(topic, course_level)


def _demo_learning_plan(topic: str, course_level: str) -> dict:
        slug = re.sub(r"[^A-Z0-9]+", "-", topic.upper()).strip("-")[:35] or "TOPIC"
        return {
            "title": f"{topic}: Foundations and Application",
            "course_context": f"A {course_level.lower()} introduction to {topic}, emphasizing conceptual understanding, application, and critical evaluation.",
            "objectives": [
                {
                    "id": f"{slug}-FOUNDATIONS",
                    "title": f"Explain {topic} fundamentals",
                    "description": f"Explain the central concepts and vocabulary of {topic} in clear, accurate language.",
                    "success_criteria": [
                        "Uses the key terminology accurately",
                        "Explains the central mechanism or idea",
                        "Connects the explanation to a relevant example",
                    ],
                    "diagnostic_prompt": f"In your own words, explain the most important idea behind {topic}. Include one concrete example and explain why it fits.",
                },
                {
                    "id": f"{slug}-APPLICATION",
                    "title": f"Apply and evaluate {topic}",
                    "description": f"Apply ideas from {topic} to a realistic situation and evaluate the result, limitation, or tradeoff.",
                    "success_criteria": [
                        "Applies the concept to the situation",
                        "Supports the reasoning with specific evidence",
                        "Identifies a limitation, risk, or tradeoff",
                    ],
                    "diagnostic_prompt": f"Describe a realistic use or case involving {topic}. Explain how the relevant concepts apply and identify one important limitation or tradeoff.",
                },
            ],
            "required_task": {
                "title": f"{topic} applied analysis",
                "description": f"Demonstrate your understanding by analyzing a realistic example involving {topic}.",
                "submission_prompt": f"Submit a concise analysis of a realistic {topic} example. Explain the relevant concepts, support your reasoning, and identify an important limitation or tradeoff.",
            },
        }
