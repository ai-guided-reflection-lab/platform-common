"""Evaluator nodes — parse per-turn adequacy, run post-session analytics."""

from __future__ import annotations

import json
import re

from langchain_core.runnables import RunnableConfig

from app.agents.state import ReflectionState
from app.services.evaluation import evaluate_transcript
from app.services.llm import get_llm_for_role


def _parse_llm_json(raw: str) -> tuple[bool, str]:
    """Parse {adequate: bool, reply: str} from raw LLM output."""
    try:
        text = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE).strip("`").strip()
        data = json.loads(text)
        return bool(data.get("adequate", False)), str(data.get("reply", raw))
    except Exception:
        return False, raw


def evaluate_reply(state: ReflectionState, config: RunnableConfig) -> dict:
    """Parse JSON reply, track wrong subtopics, advance question index, append to messages."""
    raw = state["current_reply"]
    adequate, reply = _parse_llm_json(raw)

    question_idx = state["question_idx"]
    total = state["total_questions"]
    sub_topics = state["sub_topics"]
    wrong_subtopics = list(state["wrong_subtopics"])
    is_bonus_phase = state["is_bonus_phase"]
    was_bonus = is_bonus_phase

    # Track missed subtopics for adaptive bonus
    if not adequate and not is_bonus_phase and question_idx < len(sub_topics):
        wrong_topic = sub_topics[question_idx]
        if wrong_topic not in wrong_subtopics:
            wrong_subtopics.append(wrong_topic)

    # Advance on adequate answer
    if adequate and not is_bonus_phase:
        question_idx += 1
        if question_idx >= total:
            is_bonus_phase = True
            question_idx = total

    bonus_just_started = not was_bonus and is_bonus_phase

    # Always append the parsed reply so the conversation history stays coherent.
    # bonus_transition will overwrite the last message if it needs to prepend an intro.
    messages = list(state["messages"])
    messages.append({"role": "assistant", "content": reply})

    return {
        "adequate": adequate,
        "current_reply": reply,
        "question_idx": question_idx,
        "is_bonus_phase": is_bonus_phase,
        "wrong_subtopics": wrong_subtopics,
        "bonus_just_started": bonus_just_started,
        "messages": messages,
    }


def evaluate_session(state: ReflectionState, config: RunnableConfig) -> dict:
    """Call evaluation LLM, persist ReflectionAnalytics, return result."""
    db = config["configurable"]["db"]
    llm = get_llm_for_role("evaluator")

    eval_result = evaluate_transcript(
        conversation_id=state["conversation_id"],
        transcript=state["transcript"],
        config=state["config"],
        llm=llm,
        db=db,
    )
    return {"evaluation": eval_result}
