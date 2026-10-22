from types import SimpleNamespace

import pytest

from app import lesson_flow
from test_api import lesson


def send(state, content):
    return lesson_flow.process_lesson_turn(state, SimpleNamespace(action="message", content=content))


@pytest.mark.parametrize("choice,level", list(zip(lesson_flow.FAMILIARITY_CHOICES, ["new", "some", "comfortable"])))
def test_familiarity_changes_preparation_not_quiz(choice, level):
    plan = lesson()
    state, reply, _ = send(lesson_flow.initial_state(plan), choice)
    assert state["stage"] == "study_resources"
    assert state["familiarity"] == level
    assert state["diagnostic"] == [] and state["demonstrated"] == []
    public = lesson_flow.public_state(state)
    if level == "new":
        assert plan["introductory_example"] in reply
        assert public["recommended_resource_url"] == plan["study_resources"][0]["url"]
    elif level == "some":
        assert public["study_concepts"]
        concept = plan["diagnostic_quiz"][0]["concept"]
        state, reply, _ = send(state, concept)
        assert state["study_focus"] == concept
        assert "Example:" in reply
    else:
        state, reply, _ = send(state, "Quick recap")
        assert state["stage"] == "study_resources" and "Quick recap" in reply
    state, _, _ = send(state, "I am done")
    assert state["stage"] == "diagnostic_quiz"
    assert lesson_flow.public_state(state)["current_question"]["id"] == plan["diagnostic_quiz"][0]["id"]


def test_specific_unfamiliar_concept_gets_support_and_other_topics_get_clarified():
    plan = lesson()
    concept = plan["diagnostic_quiz"][0]["concept"]
    state, reply, _ = send(lesson_flow.initial_state(plan), f"I don't understand {concept}")
    assert state["study_focus"] == concept
    assert concept in reply
    state, reply, _ = send(lesson_flow.initial_state(plan), "I don't understand interstellar unicorns")
    assert state["awaiting_study_focus"]
    assert "approved material" in reply
    assert state["demonstrated"] == []


def test_embedded_course_material_is_not_recommended_as_an_external_link():
    plan = lesson()
    plan["study_resources"] = [{
        "title": "Selected course materials", "url": "", "provider": "Instructor course materials",
        "description": "Included in the lesson.", "focus": "Study the examples.",
    }]
    state, _, _ = send(lesson_flow.initial_state(plan), "I'm completely new")
    assert lesson_flow.public_state(state)["recommended_resource_url"] is None


def test_claim_of_expertise_does_not_establish_understanding():
    state, reply, _ = send(lesson_flow.initial_state(lesson()), "I know everything")
    assert state["familiarity"] == "comfortable"
    assert state["demonstrated"] == []
    assert "quiz" in reply
