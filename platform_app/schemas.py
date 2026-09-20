from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Resource(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl


class PracticeStage(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    focus: str = Field(min_length=1, max_length=3000)


class AssessmentType(StrEnum):
    CONCEPTUAL = "conceptual"
    CODE_OUTPUT = "code_output"
    DEBUGGING = "debugging"
    CODE_CONSTRUCTION = "code_construction"
    APPLICATION_SCENARIO = "application_scenario"


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
    prerequisite_ids: list[str] = Field(default_factory=list, max_length=20)


class LearningObjective(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    concept_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    required: bool = True
    assessment_types: list[AssessmentType] = Field(default_factory=list, max_length=10)
    demonstration_assessment_types: list[AssessmentType] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_demonstration_types(self):
        unsupported = set(self.demonstration_assessment_types) - set(self.assessment_types)
        if unsupported:
            values = ", ".join(sorted(item.value for item in unsupported))
            raise ValueError(f"Demonstration assessment types must also be allowed: {values}")
        return self


class RequiredTask(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    objective_ids: list[str] = Field(min_length=1, max_length=50)


class ApprovedResource(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    document_id: str | None = Field(default=None, max_length=200)
    url: HttpUrl | None = None

    @model_validator(mode="after")
    def require_location(self):
        if not self.document_id and not self.url:
            raise ValueError("An approved resource needs a document_id or URL.")
        return self


class LearningPlan(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    course_context: str = Field(default="", max_length=2000)
    assignment_context: str = Field(default="", max_length=5000)
    concepts: list[LearningConcept] = Field(min_length=1, max_length=100)
    objectives: list[LearningObjective] = Field(min_length=1, max_length=200)
    required_task: RequiredTask
    approved_resources: list[ApprovedResource] = Field(default_factory=list, max_length=100)
    scope_notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def validate_references(self):
        concept_ids = [concept.id for concept in self.concepts]
        objective_ids = [objective.id for objective in self.objectives]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("Concept IDs must be unique.")
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("Objective IDs must be unique.")
        unknown_concepts = {o.concept_id for o in self.objectives} - set(concept_ids)
        if unknown_concepts:
            raise ValueError(f"Objectives reference unknown concepts: {', '.join(sorted(unknown_concepts))}")
        unknown_objectives = set(self.required_task.objective_ids) - set(objective_ids)
        if unknown_objectives:
            raise ValueError(f"Required task references unknown objectives: {', '.join(sorted(unknown_objectives))}")
        for concept in self.concepts:
            unknown = set(concept.prerequisite_ids) - set(concept_ids)
            if unknown:
                raise ValueError(f"Concept {concept.id} references unknown prerequisites: {', '.join(sorted(unknown))}")
            if concept.id in concept.prerequisite_ids:
                raise ValueError(f"Concept {concept.id} cannot require itself.")
        return self


class AssessmentPrompt(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    objective_id: str = Field(min_length=1, max_length=100)
    concept_id: str = Field(min_length=1, max_length=100)
    assessment_type: AssessmentType
    prompt: str = Field(min_length=1, max_length=10000)
    code: str | None = Field(default=None, max_length=20000)


class LearningEvidence(StrictModel):
    student_id: str = Field(min_length=1, max_length=200)
    course_id: str = Field(min_length=1, max_length=200)
    assignment_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    objective_id: str = Field(min_length=1, max_length=100)
    concept_id: str = Field(min_length=1, max_length=100)
    evidence_type: EvidenceType
    assessment_type: AssessmentType | None = None
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
    required_task_completed: bool = False
    objectives: list[ObjectiveProgress] = Field(default_factory=list)


class AdaptiveDecision(StrictModel):
    action: AdaptiveAction
    objective_id: str
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


class ActionInput(StrictModel):
    action: Literal["navigate", "scenario"]
    value: str = Field(min_length=1, max_length=1000)
    request_id: UUID


class GenerateTopicInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["openai", "groq"] = "openai"


class GenerateSubtopicsInput(StrictModel):
    main_topics: list[str] = Field(min_length=1, max_length=50)
