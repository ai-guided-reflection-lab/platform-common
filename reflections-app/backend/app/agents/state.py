"""Shared LangGraph state for the reflection chat system."""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class ReflectionState(TypedDict):
    # Session identity
    session_id: str
    platform_request_id: str
    student_id: str
    module_id: str

    # Config loaded from DB
    config: dict
    module_type: str
    past_weak_areas: list[str]

    # Question management
    questions: list[str]
    sub_topics: list[str]
    question_idx: int
    is_bonus_phase: bool
    wrong_subtopics: list[str]

    # Conversation history
    messages: list[dict]
    system_prompt: str

    # Current-turn I/O (set fresh each /message invocation)
    user_message: str
    current_reply: str
    adequate: bool
    bonus_just_started: bool  # True only on the turn that triggers bonus phase

    # Lifecycle
    phase: str          # "init" | "active" | "bonus_transition" | "ended"
    greeting: str
    total_questions: int

    # Populated at /end
    transcript: str
    evaluation: Optional[dict]
    conversation_id: Optional[str]
