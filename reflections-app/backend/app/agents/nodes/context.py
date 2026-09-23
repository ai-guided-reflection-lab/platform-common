"""Context nodes — load session context from DB, inject per-turn context tags."""

from __future__ import annotations

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from sqlalchemy import desc

from app.models import ModuleConfig, Conversation, ReflectionAnalytics
from app.agents.state import ReflectionState


def load_context(state: ReflectionState, config: RunnableConfig) -> dict:
    """Load ModuleConfig + past weak areas from DB. Runs once on /start."""
    db = config["configurable"]["db"]
    student_id = state["student_id"]
    module_id = state["module_id"]

    cfg = db.query(ModuleConfig).filter(ModuleConfig.module_id == module_id).first()
    if not cfg:
        raise HTTPException(404, "ModuleConfig not found — professor must configure first")

    if cfg.module.module_type == "milestone_based":
        raise HTTPException(400, "Milestone modules do not use the chat session flow")

    config_dict = {
        "required_topics": cfg.required_topics or [],
        "sub_topics": cfg.sub_topics or [],
        "expected_depth": cfg.expected_depth,
        "probing_style": cfg.probing_style,
        "must_include_application": cfg.must_include_application,
        "custom_notes": cfg.custom_notes or "",
    }

    identity_filter = (
        Conversation.platform_user_id == student_id
        if state.get("course_id")
        else Conversation.student_id == student_id
    )
    past = (
        db.query(ReflectionAnalytics)
        .join(Conversation, ReflectionAnalytics.conversation_id == Conversation.id)
        .filter(
            identity_filter,
            Conversation.module_id == module_id,
        )
        .order_by(desc(Conversation.created_at))
        .limit(3)
        .all()
    )
    past_weak = list({t for r in past for t in (r.missing_topics or [])})

    return {
        "config": config_dict,
        "module_type": cfg.module.module_type,
        "past_weak_areas": past_weak,
        "sub_topics": config_dict["sub_topics"],
    }


def inject_context(state: ReflectionState, config: RunnableConfig) -> dict:
    """Prepend [Q N/M: question] or [BONUS PHASE] tag to the user message."""
    total = state["total_questions"]
    question_idx = state["question_idx"]
    questions = state["questions"]
    is_bonus = state["is_bonus_phase"]
    wrong_subtopics = state["wrong_subtopics"]
    user_message = state["user_message"]

    if not is_bonus and question_idx < total:
        current_q = questions[question_idx]
        tagged = f"[Q{question_idx + 1}/{total}: {current_q}] {user_message}"
    elif is_bonus:
        bonus_ctx = "BONUS PHASE"
        if wrong_subtopics:
            bonus_ctx += f" - revisit weak areas: {', '.join(wrong_subtopics)}"
        tagged = f"[{bonus_ctx}] {user_message}"
    else:
        tagged = user_message

    messages = list(state["messages"])
    messages.append({"role": "user", "content": tagged})
    return {"messages": messages}
