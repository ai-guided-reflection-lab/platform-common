from copy import deepcopy

import pytest
from pydantic import ValidationError

from platform_app.schemas import (
    AssessmentType,
    LearningPlan,
    normalize_assessment_type,
    normalize_learning_plan,
)


def generic_plan() -> dict:
    return {
        "schema_version": 2,
        "title": "Membrane Transport",
        "course_context": "Introductory biology",
        "assignment_context": "Explain and apply diffusion and osmosis.",
        "concepts": [
            {
                "id": "membranes",
                "name": "Cell membranes",
                "description": "Selective permeability and concentration gradients.",
            },
            {
                "id": "osmosis",
                "name": "Osmosis",
                "prerequisite_ids": ["membranes"],
            },
        ],
        "objectives": [
            {
                "id": "BIO-1",
                "concept_id": "membranes",
                "description": "Explain diffusion across a selectively permeable membrane.",
                "success_criteria": ["Distinguishes particle movement from water movement."],
                "required": True,
                "assessment_types": ["explanation", "analysis"],
                "demonstration_requirements": [
                    {"id": "explain_diffusion", "assessment_types": ["explanation", "analysis"]}
                ],
                "anticipated_misconceptions": [
                    {
                        "id": "particles_stop",
                        "description": "Equilibrium means particles stop moving.",
                    }
                ],
            },
            {
                "id": "BIO-2",
                "concept_id": "osmosis",
                "description": "Predict water movement in a membrane scenario.",
                "success_criteria": ["Uses relative solute concentration to justify direction."],
                "required": True,
                "assessment_types": ["prediction", "application"],
                "demonstration_requirements": [
                    {"id": "predict_water", "assessment_types": ["prediction"]},
                    {"id": "apply_osmosis", "assessment_types": ["application"]},
                ],
            },
        ],
        "diagnostics": [
            {
                "id": "BIO-D1",
                "objective_id": "BIO-1",
                "assessment_type": "explanation",
                "purpose": "diagnostic",
                "prompt": "Explain why diffusion does not stop at equilibrium.",
                "evaluation_criteria": ["States that particles continue moving randomly."],
            },
            {
                "id": "BIO-D2",
                "objective_id": "BIO-2",
                "assessment_type": "prediction",
                "purpose": "diagnostic",
                "prompt": "Predict the direction of water movement in the scenario.",
                "stimulus": "A cell contains less solute than the surrounding solution.",
                "stimulus_format": "plain_text",
                "evaluation_criteria": ["Predicts water movement out of the cell."],
            },
        ],
        "required_task": {
            "id": "BIO-TASK",
            "title": "Membrane transport analysis",
            "description": "Analyze water movement in three solutions.",
            "submission_prompt": "Submit your predictions and reasoning.",
            "objective_ids": ["BIO-1", "BIO-2"],
            "submission_format": "text",
        },
        "approved_resources": [
            {
                "id": "membrane-notes",
                "title": "Membrane lecture notes",
                "document_id": "doc-1",
                "objective_ids": ["BIO-1"],
            }
        ],
        "scope": {
            "notes": "Focus on passive transport.",
            "extension_topics": ["active transport"],
            "excluded_topics": ["membrane protein synthesis"],
        },
    }


def legacy_plan() -> dict:
    return {
        "title": "Object-Oriented Programming",
        "concepts": [{"id": "classes", "name": "Classes"}],
        "objectives": [
            {
                "id": "OBJ-1",
                "concept_id": "classes",
                "description": "Explain classes and construct an instance.",
                "assessment_types": ["conceptual", "code_construction"],
                "demonstration_assessment_types": ["code_construction"],
            }
        ],
        "required_task": {
            "id": "TASK-1",
            "title": "Create a class",
            "description": "Write a small class.",
            "objective_ids": ["OBJ-1"],
        },
    }


def test_valid_generic_plan_contract():
    plan = LearningPlan.model_validate(generic_plan())

    assert plan.schema_version == 2
    assert plan.objectives[1].demonstration_requirements[1].assessment_types == [
        AssessmentType.APPLICATION
    ]
    assert plan.diagnostics[0].objective_id == "BIO-1"
    assert plan.scope.excluded_topics == ["membrane protein synthesis"]


def test_generic_plan_rejects_unknown_assessment_type():
    data = generic_plan()
    data["objectives"][0]["assessment_types"] = ["essay_magic"]
    with pytest.raises(ValidationError):
        LearningPlan.model_validate(data)


def test_generic_plan_requires_diagnostic_for_every_required_objective():
    data = generic_plan()
    data["diagnostics"] = data["diagnostics"][:1]
    with pytest.raises(ValidationError, match="diagnostic"):
        LearningPlan.model_validate(data)


def test_generic_plan_requires_demonstration_requirement_for_required_objective():
    data = generic_plan()
    data["objectives"][0]["demonstration_requirements"] = []
    with pytest.raises(ValidationError, match="demonstration requirement"):
        LearningPlan.model_validate(data)


def test_generic_plan_rejects_invalid_objective_and_diagnostic_types():
    data = generic_plan()
    data["objectives"][0]["concept_id"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="unknown concepts"):
        LearningPlan.model_validate(data)

    data = generic_plan()
    data["diagnostics"][0]["objective_id"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="unknown objectives"):
        LearningPlan.model_validate(data)

    data = generic_plan()
    data["diagnostics"][0]["assessment_type"] = "prediction"
    with pytest.raises(ValidationError, match="not permitted"):
        LearningPlan.model_validate(data)


def test_generic_plan_rejects_invalid_required_task_objective():
    data = generic_plan()
    data["required_task"]["objective_ids"] = ["UNKNOWN"]
    with pytest.raises(ValidationError, match="Required task"):
        LearningPlan.model_validate(data)


def test_generic_plan_rejects_invalid_resource_objective():
    data = generic_plan()
    data["approved_resources"][0]["objective_ids"] = ["UNKNOWN"]
    with pytest.raises(ValidationError, match="Resource"):
        LearningPlan.model_validate(data)


def test_generic_plan_rejects_cyclic_concept_prerequisites():
    data = generic_plan()
    data["concepts"][0]["prerequisite_ids"] = ["osmosis"]
    with pytest.raises(ValidationError, match="cycle"):
        LearningPlan.model_validate(data)


@pytest.mark.parametrize(
    "collection",
    ["concepts", "objectives", "diagnostics", "approved_resources"],
)
def test_generic_plan_rejects_duplicate_ids(collection):
    data = generic_plan()
    data[collection].append(deepcopy(data[collection][0]))
    with pytest.raises(ValidationError, match="unique"):
        LearningPlan.model_validate(data)


def test_generic_plan_rejects_unsatisfiable_demonstration_group():
    data = generic_plan()
    data["objectives"][0]["demonstration_requirements"][0]["assessment_types"] = [
        "prediction"
    ]
    with pytest.raises(ValidationError, match="not permitted"):
        LearningPlan.model_validate(data)


def test_legacy_phase1_plan_defaults_to_version_one_and_normalizes_types():
    plan = LearningPlan.model_validate(legacy_plan())
    normalized = normalize_learning_plan(plan)

    assert plan.schema_version == 1
    assert normalize_assessment_type(plan.objectives[0].assessment_types[0]) == AssessmentType.EXPLANATION
    assert normalize_assessment_type(AssessmentType.CODE_CONSTRUCTION) == AssessmentType.CONSTRUCTION
    assert normalize_assessment_type(AssessmentType.APPLICATION) == AssessmentType.APPLICATION
    assert normalized.objectives[0].assessment_types == [
        AssessmentType.EXPLANATION,
        AssessmentType.CONSTRUCTION,
    ]
    assert normalized.objectives[0].demonstration_requirements[0].assessment_types == [
        AssessmentType.CONSTRUCTION
    ]
    assert normalized.objectives[0].success_criteria == [plan.objectives[0].description]
    assert plan.objectives[0].assessment_types[0] == AssessmentType.CONCEPTUAL
