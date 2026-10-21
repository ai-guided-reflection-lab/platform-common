from platform_app import engines


def test_socratic_start_uses_assignment_title_and_preserves_instructor_prompt():
    assignment = {
        "tool": "socratic",
        "title": "Code review",
        "snapshot": {"config": {"prompt": "What does a reviewer check first?"}},
    }

    opening = engines.start(assignment, {"id": "attempt"})["messages"][0]["content"]

    assert "Code review" in opening
    assert "instructor's course materials" in opening
    assert "What does a reviewer check first?" in opening
    assert "simple explanation, an example, or a question to try?" in opening

    assignment["snapshot"]["config"]["prompt"] = ""
    default_opening = engines.start(assignment, {"id": "attempt"})["messages"][0]["content"]
    assert "Code review" in default_opening
    assert "What would you like to explore" not in default_opening
