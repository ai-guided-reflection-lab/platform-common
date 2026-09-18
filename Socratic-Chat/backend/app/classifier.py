from __future__ import annotations

from dataclasses import dataclass

from app.schemas import ChatMessage


@dataclass(frozen=True)
class MessageClassification:
    """Routing decision consumed by the chat endpoint."""

    needs_clarification: bool = False
    clarification_question: str | None = None
    target: str | None = None
    direct_answer: str | None = None
    rewritten_query: str | None = None


async def classify_message(
    message: str,
    history: list[ChatMessage],
) -> MessageClassification:
    """Send a normal user message through the existing RAG pipeline.

    The original classifier module is absent from the repository. This
    conservative implementation preserves the expected interface without
    guessing at answers or blocking document retrieval.
    """

    del history
    return MessageClassification(rewritten_query=message.strip())
