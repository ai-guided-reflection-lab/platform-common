"""Session nodes — build initial session state, format final transcript."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.state import ReflectionState
from app.models import Conversation
from app.services.prompts import build_reflection_prompt


def build_session(state: ReflectionState, config: RunnableConfig) -> dict:
    """Build system prompt + initial messages, set greeting."""
    questions = state["questions"]
    past_weak_areas = state.get("past_weak_areas") or []
    cfg = state["config"]

    system_prompt = build_reflection_prompt(cfg, questions, past_weak_areas)
    greeting = questions[0] if questions else "What did you learn this week?"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": greeting},
    ]

    return {
        "system_prompt": system_prompt,
        "messages": messages,
        "greeting": greeting,
        "question_idx": 0,
        "is_bonus_phase": len(questions) == 0,
        "wrong_subtopics": [],
        "phase": "active",
        "adequate": False,
        "bonus_just_started": False,
        "current_reply": "",
        "user_message": "",
        "transcript": "",
        "evaluation": None,
        "conversation_id": None,
    }


def format_transcript(state: ReflectionState, config: RunnableConfig) -> dict:
    """Strip system messages and join turns into a readable transcript. Persists Conversation."""
    db = config["configurable"]["db"]
    lines = []
    for msg in state["messages"]:
        role = msg["role"].upper()
        if role == "SYSTEM":
            continue
        lines.append(f"{role}: {msg['content']}")
    transcript = "\n\n".join(lines)

    identity = (
        {"platform_user_id": state["student_id"], "course_id": state["course_id"]}
        if state.get("course_id")
        else {"student_id": state["student_id"]}
    )
    convo = Conversation(module_id=state["module_id"], transcript=transcript, **identity)
    db.add(convo)
    db.commit()
    db.refresh(convo)

    return {
        "transcript": transcript,
        "conversation_id": convo.id,
        "phase": "ended",
    }
