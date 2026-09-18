"""Tutor node — call LLM with full message history."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.state import ReflectionState
from app.services.llm import get_llm_for_role


def call_tutor(state: ReflectionState, config: RunnableConfig) -> dict:
    """Send the current message history to the LLM and get a raw reply."""
    llm = get_llm_for_role("tutor")
    raw_reply = llm.generate(state["messages"])
    return {"current_reply": raw_reply}
