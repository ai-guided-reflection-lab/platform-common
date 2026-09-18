"""Evaluation service — send transcript to LLM, parse structured JSON, store analytics."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session as DBSession

from app.models import ReflectionAnalytics
from app.services.llm import LLMProvider
from app.services.prompts import build_evaluation_prompt

logger = logging.getLogger(__name__)


def evaluate_transcript(
    conversation_id: str,
    transcript: str,
    config: dict,
    llm: LLMProvider,
    db: DBSession,
) -> dict:
    """Evaluate a transcript and persist analytics.  Returns the evaluation dict."""
    prompt = build_evaluation_prompt(transcript, config)
    raw = llm.generate([{"role": "user", "content": prompt}])

    # Strip possible markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON: %s", raw)
        result = _fallback_result()

    # Validate / coerce fields
    result = _validate(result)

    analytics = ReflectionAnalytics(
        conversation_id=conversation_id,
        topics_covered=result.get("topics_covered", []),
        missing_topics=result.get("missing_topics", []),
        misconceptions=result.get("misconceptions", []),
        reflection_depth_score=result.get("reflection_depth_score", 0.0),
        confidence_level=result.get("confidence_level", 0),
        engagement_score=result.get("engagement_score", 0.0),
    )
    db.add(analytics)
    db.commit()
    db.refresh(analytics)
    return result


def _validate(data: dict) -> dict:
    """Coerce fields to expected types."""
    data.setdefault("topics_covered", [])
    data.setdefault("missing_topics", [])
    data.setdefault("misconceptions", [])
    data["reflection_depth_score"] = float(data.get("reflection_depth_score", 0))
    data["confidence_level"] = int(data.get("confidence_level", 0))
    data["engagement_score"] = float(data.get("engagement_score", 0))
    return data


def _fallback_result() -> dict:
    return {
        "topics_covered": [],
        "missing_topics": [],
        "misconceptions": [],
        "reflection_depth_score": 0.0,
        "confidence_level": 0,
        "engagement_score": 0.0,
    }
