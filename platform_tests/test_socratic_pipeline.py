import asyncio
from copy import deepcopy
from uuid import uuid4

from app.answer_evaluation import AnswerEvaluation
from app.classifier import MessageClassification
from app.schemas import Source
from platform_app import engines


def test_snapshot_retrieval_uses_frozen_embeddings_and_text(monkeypatch):
    chunks = [
        {
            "document_id": "doc-a",
            "chunk_id": "chunk-a",
            "title": "Unrelated notes",
            "text": "A separate topic with no matching terms.",
            "embedding": [0.0, 1.0],
        },
        {
            "document_id": "doc-b",
            "chunk_id": "chunk-b",
            "title": "Version control",
            "text": "Version control records revision history for a team.",
            "embedding": [1.0, 0.0],
        },
    ]
    frozen = deepcopy(chunks)
    monkeypatch.setattr(engines.rag, "create_embeddings", lambda _texts: [[1.0, 0.0]])

    sources = engines.rag.retrieve_snapshot("How does version control track revisions?", chunks)

    assert [source.chunk_id for source in sources] == ["chunk-b"]
    assert chunks == frozen


def test_assignment_message_uses_classifier_evaluation_and_mastery_state(monkeypatch):
    calls = []

    async def classify(message, history):
        calls.append(("classify", message, len(history)))
        return MessageClassification(
            route="learning",
            question_type="follow_up",
            target_concepts=("version control",),
            conversation_state="answering_tutor",
            dialogue_status="answering_tutor",
            conversation_action="continue",
            has_substantive_claim=True,
            target="version control",
            rewritten_query="version control tracks changes",
            confidence=0.95,
            source="rules",
        )

    source = Source(
        document_id="doc",
        chunk_id="chunk",
        title="Notes",
        text="Version control tracks revisions.",
        score=1.0,
    )
    evaluation = AnswerEvaluation(
        concept="version control",
        keyword_coverage=1.0,
        semantic_alignment=0.9,
        rubric_score=0.9,
        total_score=90,
        correctness=4,
        completeness=3,
        reasoning=3,
        application=2,
        supported_concepts=("revision history",),
        missing_concepts=(),
        critical_misconception=False,
        misconception=None,
        feedback="You connected version control to revision history.",
        confidence=0.9,
    )

    async def evaluate(message, history, sources, classification, concept_hint=None):
        calls.append(("evaluate", concept_hint, len(sources)))
        return evaluation

    async def generate(message, history, sources, classification=None, evaluation=None):
        calls.append(("generate", classification.target, evaluation.progress_status))
        return "That identifies revision history. How does it help two developers collaborate?"

    monkeypatch.setattr(engines, "classify_message", classify)
    monkeypatch.setattr(engines, "evaluate_student_answer", evaluate)
    monkeypatch.setattr(engines.rag, "retrieve_snapshot", lambda *_args, **_kwargs: [source])
    monkeypatch.setattr(engines.rag, "generate_answer", generate)

    assignment = {
        "id": uuid4(),
        "snapshot": {"config": {}, "chunks": [{"document_id": "doc"}]},
    }
    attempt = {
        "id": uuid4(),
        "messages": [{"role": "assistant", "content": "Why does version control help a team?"}],
        "engine_state": {},
    }
    result = asyncio.run(engines._socratic_message(assignment, attempt, "It tracks changes."))

    assert result["reply"].endswith("collaborate?")
    assert result["sources"][0]["document_id"] == "doc"
    assert result["socratic"]["active_concept"] == "version control"
    assert result["socratic"]["next_thinking_step"] == "How does it help two developers collaborate?"
    assert result["socratic"]["keywords"] == ["version control"]
    assert result["socratic"]["last_score"] == 90
    assert result["socratic"]["progress"]["version control"]["status"] == "developing"
    assert [call[0] for call in calls] == ["classify", "evaluate", "generate"]
