from app.services.evaluation import _validate, evaluate_transcript
from app.services.prompts import build_evaluation_prompt


def test_trajectory_evidence_survives_a_later_corrected_answer():
    result = _validate(
        {
            "topics_covered": ["String immutability"],
            "missing_topics": [],
            "misconceptions": [],
            "reflection_depth_score": 0.95,
            "confidence_level": 3,
            "engagement_score": 0.85,
        },
        wrong_subtopics=["String immutability"],
    )

    assert result["missing_topics"] == ["String immutability"]
    assert result["misconceptions"] == [
        "The student initially gave an incorrect or incomplete answer about String immutability."
    ]


def test_trajectory_reconciliation_handles_empty_and_duplicate_evidence():
    clean = _validate({})
    assert clean["missing_topics"] == []
    assert clean["misconceptions"] == []

    duplicate = _validate(
        {
            "missing_topics": ["String immutability"],
            "misconceptions": ["Incomplete understanding of String immutability"],
        },
        wrong_subtopics=["String immutability", "String immutability"],
    )
    assert duplicate["missing_topics"] == ["String immutability"]
    assert duplicate["misconceptions"] == ["Incomplete understanding of String immutability"]


def test_evaluation_prompt_distinguishes_independent_knowledge_from_repetition():
    prompt = build_evaluation_prompt(
        "USER: not sure\n\nASSISTANT: Strings are immutable for safe sharing.\n\n"
        "USER: Strings are immutable for safe sharing.",
        {"sub_topics": ["String immutability"], "expected_depth": "surface"},
        wrong_subtopics=["String immutability"],
    )

    assert "student independently demonstrated" in prompt
    assert "String immutability" in prompt
    assert "repeats or closely paraphrases" in prompt


def test_completed_evaluation_persists_known_struggle_when_model_returns_empty_gaps():
    class EmptyGapModel:
        def __init__(self):
            self.prompt = ""

        def generate(self, messages):
            self.prompt = messages[0]["content"]
            return (
                '{"topics_covered":["String immutability"],'
                '"missing_topics":[],"misconceptions":[],'
                '"reflection_depth_score":0.95,"confidence_level":3,'
                '"engagement_score":0.85}'
            )

    class RecordingDB:
        def __init__(self):
            self.analytics = None

        def add(self, analytics):
            self.analytics = analytics

        def commit(self):
            pass

        def refresh(self, analytics):
            pass

    model = EmptyGapModel()
    db = RecordingDB()
    result = evaluate_transcript(
        conversation_id="conversation-1",
        transcript=(
            "ASSISTANT: Why are strings immutable?\n\nUSER: not sure\n\n"
            "ASSISTANT: Strings are immutable for safe sharing and interning.\n\n"
            "USER: Strings are immutable for safe sharing and interning."
        ),
        config={"sub_topics": ["String immutability"], "expected_depth": "surface"},
        llm=model,
        db=db,
        wrong_subtopics=["String immutability"],
    )

    assert result["missing_topics"] == ["String immutability"]
    assert result["misconceptions"] == [
        "The student initially gave an incorrect or incomplete answer about String immutability."
    ]
    assert db.analytics.missing_topics == result["missing_topics"]
    assert db.analytics.misconceptions == result["misconceptions"]
    assert "Topics with at least one inadequate student answer: String immutability" in model.prompt
