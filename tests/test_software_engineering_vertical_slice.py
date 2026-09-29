from platform_app.adaptive import software_engineering_learning_plan
from platform_app.schemas import AssessmentType, LearningPlan


def test_seeded_software_engineering_plan_is_a_generic_v2_contract():
    plan = software_engineering_learning_plan()

    assert isinstance(plan, LearningPlan)
    assert plan.schema_version == 2
    assert [objective.id for objective in plan.objectives] == [
        "SE-REQ-TYPES",
        "SE-REQ-QUALITY",
    ]
    assert [item.objective_id for item in plan.diagnostics] == [
        "SE-REQ-TYPES",
        "SE-REQ-QUALITY",
    ]
    assert plan.diagnostics[0].assessment_type == AssessmentType.ANALYSIS
    assert plan.diagnostics[1].assessment_type == AssessmentType.DIAGNOSIS
    assert plan.concepts[1].prerequisite_ids == ["requirement_types"]
    assert plan.required_task.objective_ids == [
        "SE-REQ-TYPES",
        "SE-REQ-QUALITY",
    ]


def test_seeded_software_engineering_plan_contains_no_oop_runtime_assumptions():
    serialized = software_engineering_learning_plan().model_dump_json()

    for legacy_term in ("BankAccount", "OBJ-1", "Python"):
        assert legacy_term not in serialized
