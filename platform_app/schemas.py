from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictInt, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Resource(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl


class PracticeStage(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    focus: str = Field(min_length=1, max_length=3000)


class AssessmentType(StrEnum):
    # Generic Phase 2 vocabulary.
    EXPLANATION = "explanation"
    ANALYSIS = "analysis"
    PREDICTION = "prediction"
    APPLICATION = "application"
    CONSTRUCTION = "construction"
    DIAGNOSIS = "diagnosis"

    # Phase 1 values remain valid for published snapshots and stored evidence.
    CONCEPTUAL = "conceptual"
    CODE_OUTPUT = "code_output"
    DEBUGGING = "debugging"
    CODE_CONSTRUCTION = "code_construction"
    APPLICATION_SCENARIO = "application_scenario"


LEGACY_ASSESSMENT_TYPE_MAP = {
    AssessmentType.CONCEPTUAL: AssessmentType.EXPLANATION,
    AssessmentType.CODE_OUTPUT: AssessmentType.PREDICTION,
    AssessmentType.DEBUGGING: AssessmentType.DIAGNOSIS,
    AssessmentType.CODE_CONSTRUCTION: AssessmentType.CONSTRUCTION,
    AssessmentType.APPLICATION_SCENARIO: AssessmentType.APPLICATION,
}


def normalize_assessment_type(value: AssessmentType | str) -> AssessmentType:
    """Return the domain-neutral equivalent without mutating legacy data."""
    assessment_type = AssessmentType(value)
    return LEGACY_ASSESSMENT_TYPE_MAP.get(assessment_type, assessment_type)


class EvidenceType(StrEnum):
    SELF_REPORT = "self_report"
    DIAGNOSTIC_RESPONSE = "diagnostic_response"
    GUIDED_RESPONSE = "guided_response"
    PRACTICE_ATTEMPT = "practice_attempt"
    INDEPENDENT_APPLICATION = "independent_application"
    REQUIRED_TASK_SUBMISSION = "required_task_submission"


class CorrectnessState(StrEnum):
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    CORRECT = "correct"


class CompletenessState(StrEnum):
    INCOMPLETE = "incomplete"
    PARTIAL = "partial"
    COMPLETE = "complete"


class IndependenceLevel(StrEnum):
    GUIDED = "guided"
    SUPPORTED = "supported"
    INDEPENDENT = "independent"


class ObjectiveStatus(StrEnum):
    NOT_OBSERVED = "not_observed"
    EMERGING = "emerging"
    DEVELOPING = "developing"
    DEMONSTRATED = "demonstrated"
    NEEDS_REVIEW = "needs_review"


class RequiredTaskStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AdaptiveAction(StrEnum):
    ASSESS = "ASSESS"
    EXPLAIN = "EXPLAIN"
    HINT = "HINT"
    PRACTICE = "PRACTICE"
    REMEDIATE = "REMEDIATE"
    ADVANCE = "ADVANCE"
    CHALLENGE = "CHALLENGE"
    FOCUS_REQUIRED = "FOCUS_REQUIRED"


class LearningConcept(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    prerequisite_ids: list[str] = Field(default_factory=list, max_length=20)


class EvidenceRequirement(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    assessment_types: list[AssessmentType] = Field(min_length=1, max_length=10)


class AnticipatedMisconception(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(min_length=1, max_length=2000)


class LearningObjective(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    concept_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    success_criteria: list[str] = Field(default_factory=list, max_length=20)
    required: bool = True
    assessment_types: list[AssessmentType] = Field(default_factory=list, max_length=10)
    demonstration_assessment_types: list[AssessmentType] = Field(default_factory=list, max_length=10)
    demonstration_requirements: list[EvidenceRequirement] = Field(default_factory=list, max_length=10)
    anticipated_misconceptions: list[AnticipatedMisconception] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_demonstration_types(self):
        unsupported = set(self.demonstration_assessment_types) - set(self.assessment_types)
        if unsupported:
            values = ", ".join(sorted(item.value for item in unsupported))
            raise ValueError(f"Demonstration assessment types must also be allowed: {values}")
        return self


class AssessmentItem(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    objective_id: str = Field(min_length=1, max_length=100)
    assessment_type: AssessmentType
    purpose: Literal["diagnostic", "formative"]
    prompt: str = Field(min_length=1, max_length=10000)
    stimulus: str | None = Field(default=None, max_length=20000)
    stimulus_format: Literal["plain_text", "code", "table", "equation"] = "plain_text"
    evaluation_criteria: list[str] = Field(min_length=1, max_length=20)


class RequiredTask(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    submission_prompt: str = Field(default="", max_length=5000)
    objective_ids: list[str] = Field(min_length=1, max_length=50)
    submission_format: Literal["text"] = "text"


class ApprovedResource(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    document_id: str | None = Field(default=None, max_length=200)
    url: HttpUrl | None = None
    objective_ids: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def require_location(self):
        if not self.document_id and not self.url:
            raise ValueError("An approved resource needs a document_id or URL.")
        return self


class LearningScope(StrictModel):
    notes: str = Field(default="", max_length=5000)
    extension_topics: list[str] = Field(default_factory=list, max_length=100)
    excluded_topics: list[str] = Field(default_factory=list, max_length=100)


class LearningPlan(StrictModel):
    schema_version: Literal[1, 2] = 1
    title: str = Field(min_length=1, max_length=300)
    course_context: str = Field(default="", max_length=2000)
    assignment_context: str = Field(default="", max_length=5000)
    concepts: list[LearningConcept] = Field(min_length=1, max_length=100)
    objectives: list[LearningObjective] = Field(min_length=1, max_length=200)
    diagnostics: list[AssessmentItem] = Field(default_factory=list, max_length=500)
    required_task: RequiredTask
    approved_resources: list[ApprovedResource] = Field(default_factory=list, max_length=100)
    scope: LearningScope = Field(default_factory=LearningScope)
    scope_notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def validate_references(self):
        concept_ids = [concept.id for concept in self.concepts]
        objective_ids = [objective.id for objective in self.objectives]
        diagnostic_ids = [item.id for item in self.diagnostics]
        resource_ids = [item.id for item in self.approved_resources]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("Concept IDs must be unique.")
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("Objective IDs must be unique.")
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("Diagnostic IDs must be unique.")
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError("Resource IDs must be unique.")
        unknown_concepts = {o.concept_id for o in self.objectives} - set(concept_ids)
        if unknown_concepts:
            raise ValueError(f"Objectives reference unknown concepts: {', '.join(sorted(unknown_concepts))}")
        unknown_objectives = set(self.required_task.objective_ids) - set(objective_ids)
        if unknown_objectives:
            raise ValueError(f"Required task references unknown objectives: {', '.join(sorted(unknown_objectives))}")
        if len(self.required_task.objective_ids) != len(set(self.required_task.objective_ids)):
            raise ValueError("Required task objective IDs must be unique.")

        graph = {concept.id: concept.prerequisite_ids for concept in self.concepts}
        for concept in self.concepts:
            unknown = set(concept.prerequisite_ids) - set(concept_ids)
            if unknown:
                raise ValueError(f"Concept {concept.id} references unknown prerequisites: {', '.join(sorted(unknown))}")
            if concept.id in concept.prerequisite_ids:
                raise ValueError(f"Concept {concept.id} cannot require itself.")
            if len(concept.prerequisite_ids) != len(set(concept.prerequisite_ids)):
                raise ValueError(f"Concept {concept.id} prerequisite IDs must be unique.")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(concept_id: str):
            if concept_id in visiting:
                raise ValueError("Concept prerequisites contain a cycle.")
            if concept_id in visited:
                return
            visiting.add(concept_id)
            for prerequisite_id in graph[concept_id]:
                visit(prerequisite_id)
            visiting.remove(concept_id)
            visited.add(concept_id)

        for concept_id in concept_ids:
            visit(concept_id)

        objectives = {objective.id: objective for objective in self.objectives}
        for item in self.diagnostics:
            objective = objectives.get(item.objective_id)
            if objective is None:
                raise ValueError(f"Diagnostics reference unknown objectives: {item.objective_id}")
            if item.assessment_type not in objective.assessment_types:
                raise ValueError(
                    f"Diagnostic {item.id} uses an assessment type not permitted for objective {objective.id}."
                )

        for resource in self.approved_resources:
            unknown = set(resource.objective_ids) - set(objective_ids)
            if unknown:
                raise ValueError(
                    f"Resource {resource.id} references unknown objectives: {', '.join(sorted(unknown))}"
                )
            if len(resource.objective_ids) != len(set(resource.objective_ids)):
                raise ValueError(f"Resource {resource.id} objective IDs must be unique.")

        if self.schema_version == 2:
            generic_types = {
                AssessmentType.EXPLANATION,
                AssessmentType.ANALYSIS,
                AssessmentType.PREDICTION,
                AssessmentType.APPLICATION,
                AssessmentType.CONSTRUCTION,
                AssessmentType.DIAGNOSIS,
            }
            requirement_ids: list[str] = []
            for objective in self.objectives:
                if not objective.success_criteria or any(not value for value in objective.success_criteria):
                    raise ValueError(f"Objective {objective.id} requires success criteria.")
                if not objective.assessment_types:
                    raise ValueError(f"Objective {objective.id} requires assessment types.")
                legacy_types = set(objective.assessment_types) - generic_types
                if legacy_types:
                    values = ", ".join(sorted(item.value for item in legacy_types))
                    raise ValueError(f"Phase 2 objective {objective.id} uses legacy assessment types: {values}")
                if objective.demonstration_assessment_types:
                    raise ValueError(
                        f"Phase 2 objective {objective.id} must use demonstration requirements."
                    )
                if objective.required and not objective.demonstration_requirements:
                    raise ValueError(
                        f"Required objective {objective.id} needs at least one demonstration requirement."
                    )
                for requirement in objective.demonstration_requirements:
                    requirement_ids.append(requirement.id)
                    unsupported = set(requirement.assessment_types) - set(objective.assessment_types)
                    if unsupported:
                        values = ", ".join(sorted(item.value for item in unsupported))
                        raise ValueError(
                            f"Demonstration requirement {requirement.id} uses assessment types not permitted "
                            f"for objective {objective.id}: {values}"
                        )
                misconception_ids = [item.id for item in objective.anticipated_misconceptions]
                if len(misconception_ids) != len(set(misconception_ids)):
                    raise ValueError(f"Objective {objective.id} misconception IDs must be unique.")
            if len(requirement_ids) != len(set(requirement_ids)):
                raise ValueError("Demonstration requirement IDs must be unique.")

            diagnostic_objectives = {
                item.objective_id for item in self.diagnostics if item.purpose == "diagnostic"
            }
            missing = {
                objective.id
                for objective in self.objectives
                if objective.required and objective.id not in diagnostic_objectives
            }
            if missing:
                raise ValueError(
                    f"Every required objective needs a diagnostic; missing: {', '.join(sorted(missing))}"
                )
            if not self.required_task.submission_prompt:
                raise ValueError("Phase 2 required task needs a submission prompt.")
        return self


def normalize_learning_plan(value: LearningPlan | dict) -> LearningPlan:
    """Return a non-mutating plan view using the generic assessment vocabulary.

    Legacy plans remain schema version 1 because their diagnostics and required-task
    contract are supplied by the Phase 1 runtime. This function only normalizes the
    fields that have an exact Phase 2 equivalent; it never rewrites a snapshot.
    """
    plan = value if isinstance(value, LearningPlan) else LearningPlan.model_validate(value)
    if plan.schema_version == 2:
        return plan.model_copy(deep=True)

    objectives: list[LearningObjective] = []
    for index, objective in enumerate(plan.objectives):
        allowed = list(dict.fromkeys(normalize_assessment_type(item) for item in objective.assessment_types))
        demonstration_types = list(
            dict.fromkeys(
                normalize_assessment_type(item)
                for item in objective.demonstration_assessment_types
            )
        )
        requirements = [
            requirement.model_copy(
                update={
                    "assessment_types": list(
                        dict.fromkeys(
                            normalize_assessment_type(item)
                            for item in requirement.assessment_types
                        )
                    )
                },
                deep=True,
            )
            for requirement in objective.demonstration_requirements
        ]
        if not requirements and demonstration_types:
            requirements = [
                EvidenceRequirement(
                    id=f"legacy_demo_{index + 1}",
                    assessment_types=demonstration_types,
                )
            ]
        objectives.append(
            objective.model_copy(
                update={
                    "success_criteria": objective.success_criteria or [objective.description],
                    "assessment_types": allowed,
                    "demonstration_assessment_types": [],
                    "demonstration_requirements": requirements,
                },
                deep=True,
            )
        )

    diagnostics = [
        item.model_copy(
            update={"assessment_type": normalize_assessment_type(item.assessment_type)},
            deep=True,
        )
        for item in plan.diagnostics
    ]
    return plan.model_copy(
        update={"objectives": objectives, "diagnostics": diagnostics},
        deep=True,
    )


class AssessmentPrompt(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    objective_id: str = Field(min_length=1, max_length=100)
    concept_id: str = Field(min_length=1, max_length=100)
    assessment_type: AssessmentType
    prompt: str = Field(min_length=1, max_length=10000)
    code: str | None = Field(default=None, max_length=20000)


class AssessmentResult(StrictModel):
    objective_id: str = Field(min_length=1, max_length=100)
    assessment_type: AssessmentType
    correctness: CorrectnessState
    completeness: CompletenessState
    independence: IndependenceLevel
    misconception_code: str | None = Field(default=None, max_length=200)
    misconception_detail: str | None = Field(default=None, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)
    assessor_version: str = Field(min_length=1, max_length=100)


class LearningEvidence(StrictModel):
    student_id: str = Field(min_length=1, max_length=200)
    course_id: str = Field(min_length=1, max_length=200)
    assignment_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    objective_id: str = Field(min_length=1, max_length=100)
    concept_id: str = Field(min_length=1, max_length=100)
    evidence_type: EvidenceType
    assessment_type: AssessmentType | None = None
    assessment_id: str | None = Field(default=None, max_length=100)
    assessment_origin: Literal["authored", "legacy", "required_task", "generated"] | None = None
    assessment_prompt: str | None = Field(default=None, max_length=20000)
    response: str = Field(default="", max_length=20000)
    correctness: CorrectnessState
    completeness: CompletenessState
    independence: IndependenceLevel
    hints_used: int = Field(default=0, ge=0, le=100)
    misconception_code: str | None = Field(default=None, max_length=200)
    misconception_detail: str | None = Field(default=None, max_length=2000)
    assessor_version: str = Field(min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ObjectiveProgress(StrictModel):
    objective_id: str
    concept_id: str
    status: ObjectiveStatus = ObjectiveStatus.NOT_OBSERVED
    evidence_count: int = Field(default=0, ge=0)
    independent_evidence_count: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    hints_used: int = Field(default=0, ge=0)
    last_updated_at: datetime | None = None


class AttemptLearningState(StrictModel):
    """Completion flags are deliberately independent of objective mastery."""
    assignment_completed: bool = False
    required_task_status: RequiredTaskStatus = RequiredTaskStatus.NOT_STARTED
    objectives: list[ObjectiveProgress] = Field(default_factory=list)


class AdaptiveDecision(StrictModel):
    action: AdaptiveAction
    objective_id: str
    assessment_type: AssessmentType | None = None
    assessment_id: str | None = Field(default=None, max_length=100)
    prompt_source: Literal["authored", "legacy", "required_task", "generated"] | None = None
    reason_codes: list[str] = Field(min_length=1, max_length=20)
    policy_version: str
    resume_objective_id: str | None = None


class ClassObjectiveAnalytics(StrictModel):
    objective_id: str
    concept_id: str
    status_counts: dict[ObjectiveStatus, int] = Field(default_factory=dict)
    common_misconceptions: dict[str, int] = Field(default_factory=dict)
    remediation_count: int = 0
    independent_demonstration_count: int = 0


class Topic(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    resource: Resource
    alt_resource: Resource
    practice_label: str = Field(min_length=1, max_length=300)
    practice_prompt: str = Field(min_length=1, max_length=10000)
    practice_stages: list[PracticeStage] = Field(min_length=1, max_length=20)
    practice_options: list[str] = Field(default_factory=list, max_length=20)
    check_questions: list[str] = Field(default_factory=list, max_length=50)
    final_example: str = Field(min_length=1, max_length=20000)
    number: int = 100


class SocraticConfig(StrictModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    prompt: str = Field(default="", max_length=10000)
    minimum_messages: int = Field(default=1, ge=1, le=100)


class ReflectionConfig(StrictModel):
    module_type: Literal["topic_based", "milestone_based"] = "topic_based"
    required_topics: list[str] = Field(default_factory=list, max_length=100)
    sub_topics: list[str] = Field(default_factory=list, max_length=100)
    expected_depth: Literal["surface", "applied", "analytical"] = "surface"
    probing_style: Literal["supportive", "socratic"] = "supportive"
    must_include_application: bool = False
    custom_notes: str = Field(default="", max_length=10000)
    milestone_prompt: str = Field(default="", max_length=10000)
    historical_data: str = Field(default="", max_length=2_000_000)

    def validate_publish(self):
        if self.module_type == "topic_based":
            if not any(t.strip() for t in self.sub_topics):
                raise ValueError("Add at least one reflection sub-topic before publishing.")
        else:
            if not self.milestone_prompt or not self.historical_data:
                raise ValueError("Milestone reflections require a prompt and historical CSV.")
            reader = csv.DictReader(io.StringIO(self.historical_data))
            if not {"name", "challenge", "solution"}.issubset(reader.fieldnames or []):
                raise ValueError("Historical CSV must contain name, challenge, and solution columns.")
            if not any(all((row.get(k) or "").strip() for k in ("name", "challenge", "solution")) for row in reader):
                raise ValueError("Historical CSV must contain at least one complete row.")


class TutorConfig(StrictModel):
    topic: Topic | None = None
    learning_plan: LearningPlan | None = None
    provider: Literal["openai", "groq"] = "openai"
    personality: str = "confused"


CONFIG_MODELS = {"socratic": SocraticConfig, "reflections": ReflectionConfig, "student-agent": TutorConfig}


class AssignmentInput(StrictModel):
    course_id: UUID
    tool: Literal["socratic", "reflections", "student-agent"]
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=10000)
    due_at: datetime | None = None
    audience: Literal["course", "selected"] = "course"
    recipient_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self):
        self.config = CONFIG_MODELS[self.tool].model_validate(self.config).model_dump(mode="json")
        if self.due_at and self.due_at.tzinfo is None:
            raise ValueError("Due date must include a time zone.")
        if self.audience == "selected" and not self.recipient_ids:
            raise ValueError("Select at least one student.")
        return self


class MessageInput(StrictModel):
    message: str = Field(min_length=1, max_length=20000)
    request_id: UUID


class SelfDirectedStudyInput(StrictModel):
    message: str = Field(default="I've finished studying", min_length=1, max_length=300)


class SelfDirectedQuizInput(StrictModel):
    answers: list[int] = Field(min_length=5, max_length=5)


class SelfDirectedMessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=8000)


class SelfDirectedTaskInput(StrictModel):
    content: str = Field(min_length=1, max_length=20000)


class SelfDirectedLearningTurn(StrictModel):
    action: Literal["message", "answer", "hint", "continue", "choice", "pause", "resume"] = "message"
    content: str = Field(default="", max_length=8000)
    question_id: str | None = Field(default=None, max_length=80)
    option_index: StrictInt | None = Field(default=None, ge=0, le=3)
    confidence: Literal["low", "medium", "high"] | None = None
    explanation: str | None = Field(default=None, max_length=3000)
    turn_id: str = Field(min_length=1, max_length=100)


class ActionInput(StrictModel):
    action: Literal["navigate", "scenario"]
    value: str = Field(min_length=1, max_length=1000)
    request_id: UUID


class GenerateTopicInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["openai", "groq"] = "openai"


class GenerateSubtopicsInput(StrictModel):
    main_topics: list[str] = Field(min_length=1, max_length=50)
