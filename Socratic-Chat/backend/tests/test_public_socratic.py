import asyncio
from unittest.mock import AsyncMock

from app import main
from app.classifier import MessageClassification
from app.schemas import PublicSocraticRequest
from platform_app import engines


def test_public_message_reuses_socratic_pipeline_without_private_retrieval(monkeypatch):
    classification = MessageClassification(
        route="learning",
        question_type="what",
        target_concepts=("version control",),
        conversation_state="new_concept",
        dialogue_status="new_topic",
        conversation_action="continue",
        target="version control",
        rewritten_query="version control",
        confidence=0.95,
        source="rules",
    )
    calls = []

    async def classify(message, history, learning_topic=None):
        calls.append(("classify", message, learning_topic, len(history)))
        return classification

    async def evaluate(*args, **kwargs):
        calls.append(("evaluate", kwargs["evidence_scope"]))
        return None

    async def generate(question, history, sources, **kwargs):
        calls.append((
            "generate", question, sources[0].document_id,
            kwargs["grounding_mode"], kwargs["learning_topic"],
        ))
        return "Imagine two developers edit the same file. What problem could version control prevent?"

    monkeypatch.setattr(engines, "classify_message", classify)
    monkeypatch.setattr(engines, "evaluate_student_answer", evaluate)
    monkeypatch.setattr(engines.rag, "generate_answer", generate)

    result, topic = asyncio.run(
        engines.public_socratic_message("What is version control?", [], {})
    )

    assert topic == "What is version control?"
    assert result["reply"].endswith("?")
    assert result["socratic"]["active_concept"] == "version control"
    assert calls == [
        ("classify", "What is version control?", None, 0),
        ("evaluate", "general"),
        ("generate", "version control", "public-learning-topic", "general", "What is version control?"),
    ]


def test_public_endpoint_returns_widget_contract(monkeypatch):
    monkeypatch.setattr(
        main.platform_engines,
        "public_socratic_message",
        AsyncMock(return_value=(
            {"reply": "Which consequence matters most?", "socratic": {"active_concept": "trade-offs"}},
            "How should I reason about trade-offs?",
        )),
    )

    response = asyncio.run(main.public_socratic_chat(PublicSocraticRequest(
        message="They affect cost.",
        conversation_id="thread-1",
        history=[],
        engine_state={"support_level": 1},
    )))

    assert response.model_dump() == {
        "answer": "Which consequence matters most?",
        "conversation_id": "thread-1",
        "learning_topic": "How should I reason about trade-offs?",
        "socratic": {"active_concept": "trade-offs"},
    }
