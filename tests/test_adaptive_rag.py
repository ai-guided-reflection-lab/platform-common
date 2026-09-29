from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Socratic-Chat/backend"))

from platform_app import engines
from platform_app.adaptive import software_engineering_learning_plan
from platform_app.schemas import AdaptiveAction, AdaptiveDecision


COURSE_ID = "course-a"


def scoped_plan() -> dict:
    plan = software_engineering_learning_plan().model_dump(mode="json")
    plan["approved_resources"] = [
        {
            "id": "types-notes",
            "title": "Requirement types notes",
            "document_id": "doc-types",
            "objective_ids": ["SE-REQ-TYPES"],
        },
        {
            "id": "quality-notes",
            "title": "Requirement quality notes",
            "document_id": "doc-quality",
            "objective_ids": ["SE-REQ-QUALITY"],
        },
        {
            "id": "shared-notes",
            "title": "Shared requirements notes",
            "document_id": "doc-shared",
            "objective_ids": [],
        },
        {
            "id": "excluded-topic-notes",
            "title": "Formal specification languages",
            "document_id": "doc-excluded",
            "objective_ids": [],
        },
        {
            "id": "cross-course-notes",
            "title": "Cross-course notes",
            "document_id": "doc-cross-course",
            "objective_ids": [],
        },
    ]
    return plan


def chunks() -> list[dict]:
    return [
        {
            "document_id": "doc-types",
            "chunk_id": "doc-types:0",
            "course_id": COURSE_ID,
            "title": "Requirement types notes",
            "text": "Functional requirements describe system behavior; non-functional requirements describe quality constraints.",
            "tokens": ["functional", "requirements", "describe", "system", "behavior", "non", "quality", "constraints"],
        },
        {
            "document_id": "doc-quality",
            "chunk_id": "doc-quality:0",
            "course_id": COURSE_ID,
            "title": "Requirement quality notes",
            "text": "Ambiguous requirements use vague words; improve them with measurable, testable conditions.",
            "tokens": ["ambiguous", "requirements", "vague", "words", "improve", "measurable", "testable", "conditions"],
        },
        {
            "document_id": "doc-shared",
            "chunk_id": "doc-shared:0",
            "course_id": COURSE_ID,
            "title": "Shared requirements notes",
            "text": "Improve requirement classification with clear, testable, concrete evidence.",
            "tokens": ["improve", "requirement", "classification", "clear", "testable", "concrete", "evidence"],
        },
        {
            "document_id": "doc-excluded",
            "chunk_id": "doc-excluded:0",
            "course_id": COURSE_ID,
            "title": "Formal specification languages",
            "text": "Formal specification languages describe requirements with mathematical notation.",
            "tokens": ["formal", "specification", "languages", "describe", "requirements", "mathematical", "notation"],
        },
        {
            "document_id": "doc-other",
            "chunk_id": "doc-other:0",
            "course_id": COURSE_ID,
            "title": "Another assignment",
            "text": "Functional and non-functional requirements from another assignment.",
            "tokens": ["functional", "non", "requirements", "another", "assignment"],
        },
        {
            "document_id": "doc-cross-course",
            "chunk_id": "doc-cross-course:0",
            "course_id": "course-b",
            "title": "Cross-course notes",
            "text": "Functional and non-functional requirements from another course.",
            "tokens": ["functional", "non", "requirements", "another", "course"],
        },
    ]


def decision(objective_id: str) -> AdaptiveDecision:
    return AdaptiveDecision(
        action=AdaptiveAction.EXPLAIN,
        objective_id=objective_id,
        reason_codes=["incorrect_evidence"],
        policy_version="adaptive-sdl-v2",
    )


def assignment(plan: dict | None = None, snapshot_chunks: list[dict] | None = None) -> dict:
    published_plan = plan or scoped_plan()
    return {
        "id": "assignment-a",
        "course_id": COURSE_ID,
        "config": {"learning_plan": {"title": "unpublished draft"}},
        "snapshot": {
            "config": {"learning_plan": published_plan},
            "chunks": chunks() if snapshot_chunks is None else snapshot_chunks,
        },
    }


def test_adaptive_rag_uses_only_published_objective_and_plan_wide_resources():
    plan = software_engineering_learning_plan()
    item = assignment()

    types_context = engines.adaptive_rag_context(
        item,
        plan.objectives[0],
        decision("SE-REQ-TYPES"),
        "Why is this requirement functional?",
    )
    quality_context = engines.adaptive_rag_context(
        item,
        plan.objectives[1],
        decision("SE-REQ-QUALITY"),
        "Why is this requirement ambiguous and how can I improve it?",
    )

    assert {source["resource_id"] for source in types_context} == {
        "types-notes",
        "shared-notes",
    }
    assert {source["resource_id"] for source in quality_context} == {
        "quality-notes",
        "shared-notes",
    }
    assert all(source["course_id"] == COURSE_ID for source in types_context + quality_context)
    assert all(source["chunk_id"] for source in types_context + quality_context)
    assert "excluded-topic-notes" not in {
        source["resource_id"] for source in types_context + quality_context
    }
    assert "cross-course-notes" not in {
        source["resource_id"] for source in types_context + quality_context
    }


def test_adaptive_rag_cannot_read_other_assignment_or_unpublished_plan_state():
    published = scoped_plan()
    item = assignment(published)
    item["config"] = {
        "learning_plan": {
            **published,
            "approved_resources": [
                {
                    "id": "draft-only",
                    "title": "Draft-only notes",
                    "document_id": "doc-other",
                    "objective_ids": [],
                }
            ],
        }
    }
    objective = software_engineering_learning_plan().objectives[0]

    context = engines.adaptive_rag_context(
        item,
        objective,
        decision(objective.id),
        "functional non-functional requirements",
    )

    assert "doc-other" not in {source["document_id"] for source in context}
    assert "draft-only" not in {source["resource_id"] for source in context}
    assert {source["document_id"] for source in context} <= {
        "doc-types",
        "doc-shared",
    }


def test_adaptive_rag_no_relevant_snapshot_content_returns_empty_context():
    plan = scoped_plan()
    irrelevant = [
        {
            "document_id": "doc-types",
            "chunk_id": "doc-types:irrelevant",
            "course_id": COURSE_ID,
            "title": "Requirement types notes",
            "text": "Chlorophyll captures sunlight during photosynthesis.",
            "tokens": ["chlorophyll", "captures", "sunlight", "photosynthesis"],
        }
    ]
    objective = software_engineering_learning_plan().objectives[0]

    assert engines.adaptive_rag_context(
        assignment(plan, irrelevant),
        objective,
        decision(objective.id),
        "Why is this requirement functional?",
    ) == []
