from platform_app import engines


def test_keyword_assignment_starts_with_frozen_course_example():
    snapshot = {
        "config": {"prompt": ""},
        "approved_keywords": ["code review", "correctness"],
        "chunks": [
            {"text": "Code review is important to quality."},
            {"text": "When a teammate checks a proposed change, they look for correctness before merging it."},
        ],
    }
    assignment = {"tool": "socratic", "title": "Assignment 6", "snapshot": snapshot}

    result = engines.start(assignment, {})
    opening = result["messages"][0]["content"]

    assert "**code review**" in opening
    assert "When a teammate checks a proposed change" in opening
    assert opening.endswith("how does it relate to code review?")
    assert result["socratic"]["objective_keywords"] == ["code review", "correctness"]
    assert snapshot["chunks"][1]["text"] in opening


def test_keyword_objective_keeps_its_diagnostic_question_after_example():
    assignment = {
        "tool": "socratic",
        "snapshot": {
            "config": {},
            "chunks": [{"text": "When a reviewer reads a patch, they check correctness before it is merged."}],
            "learning_objective": {
                "keywords": ["code review", "correctness"],
                "diagnostic_question": "What should a reviewer check, and why?",
                "objective_id": "objective-1",
            },
        },
    }

    opening = engines.start(assignment, {})["messages"][0]["content"]

    assert "When a reviewer reads a patch" in opening
    assert opening.endswith("What should a reviewer check, and why?")


def test_keyword_opening_does_not_reference_an_example_it_cannot_show():
    assignment = {
        "tool": "socratic",
        "snapshot": {
            "config": {},
            "approved_keywords": ["code review"],
            "chunks": [{"text": "A brief, unrelated note."}],
        },
    }

    opening = engines.start(assignment, {})["messages"][0]["content"]

    assert "example" not in opening.casefold()
    assert opening.endswith("What do you already know about code review?")
