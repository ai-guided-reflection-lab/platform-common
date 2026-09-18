"""Planner nodes — generate questions, route phase transitions, handle bonus start."""

from __future__ import annotations

import json
import re

from langchain_core.runnables import RunnableConfig

from app.agents.state import ReflectionState
from app.services.llm import get_llm_for_role
from app.services.prompts import build_question_generation_prompt


def _parse_questions(raw: str, sub_topics: list[str]) -> list[str]:
    """Parse LLM JSON array of questions with per-topic fallback."""
    try:
        text = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE).strip("`").strip()
        questions = json.loads(text)
        if not isinstance(questions, list):
            raise ValueError("not a list")
        result = []
        for i, topic in enumerate(sub_topics):
            if i < len(questions) and isinstance(questions[i], str) and questions[i].strip():
                result.append(questions[i].strip())
            else:
                result.append(f"What do you know about {topic}?")
        return result
    except Exception:
        return [f"What do you know about {topic}?" for topic in sub_topics]


def generate_questions(state: ReflectionState, config: RunnableConfig) -> dict:
    """Call LLM to produce one question per sub_topic."""
    sub_topics = state["sub_topics"]
    if not sub_topics:
        return {"questions": [], "total_questions": 0}

    llm = get_llm_for_role("planner")
    prompt = build_question_generation_prompt(sub_topics, state["config"])
    raw = llm.generate([{"role": "user", "content": prompt}])
    questions = _parse_questions(raw, sub_topics)
    return {"questions": questions, "total_questions": len(questions)}


def route_phase(state: ReflectionState, config: RunnableConfig) -> str:
    """Conditional edge: did we just transition into bonus phase?"""
    if state.get("bonus_just_started"):
        return "bonus_transition"
    return "end"


def bonus_transition(state: ReflectionState, config: RunnableConfig) -> dict:
    """Replace last assistant message with intro + ask first bonus question (second LLM call)."""
    llm = get_llm_for_role("tutor")
    wrong_subtopics = state["wrong_subtopics"]
    reply = state["current_reply"]  # already parsed plain text reply

    if wrong_subtopics:
        weak_str = ", ".join(wrong_subtopics)
        intro = f"Since you had some trouble with {weak_str}, let's chat more on that."
    else:
        intro = "Great work covering all the questions! Let's explore some deeper topics."

    transition = reply + " " + intro

    # Replace the reply evaluate_reply already appended with the richer transition message.
    messages = list(state["messages"])
    if messages and messages[-1]["role"] == "assistant":
        messages[-1] = {"role": "assistant", "content": transition}
    else:
        messages.append({"role": "assistant", "content": transition})

    bonus_ctx = "BONUS PHASE"
    if wrong_subtopics:
        bonus_ctx += f" - revisit: {', '.join(wrong_subtopics)}"
    messages.append({"role": "user", "content": f"[{bonus_ctx}] (ready for first bonus question)"})

    raw_bonus = llm.generate(messages)
    try:
        text = re.sub(r"^```[a-z]*\n?", "", raw_bonus.strip(), flags=re.MULTILINE).strip("`").strip()
        data = json.loads(text)
        bonus_q = str(data.get("reply", raw_bonus))
    except Exception:
        bonus_q = raw_bonus

    messages.append({"role": "assistant", "content": bonus_q})

    full_reply = transition + "\n\n" + bonus_q
    return {"messages": messages, "current_reply": full_reply, "bonus_just_started": False}
