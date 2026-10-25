from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from platform_app.schemas import (
    AssignmentInput, CONFIG_MODELS, ReflectionCopilotEvidence,
    ReflectionCopilotProposal, StrictModel, _copilot_document_ids,
)

Activity = Literal["socratic", "reflections", "self-directed-learning", "debate"]


class CurrentDraft(StrictModel):
    title: str = Field(default="", max_length=200)
    instructions: str = Field(default="", max_length=10000)
    tool: Activity | None = None
    module_type: Literal["topic_based", "milestone_based"] = "topic_based"


class CopilotRequest(StrictModel):
    course_id: UUID
    request_id: UUID = Field(default_factory=uuid4)
    goal: str = Field(min_length=10, max_length=2000)
    document_ids: list[str] = Field(min_length=1, max_length=100)
    current: CurrentDraft = Field(default_factory=CurrentDraft)
    revision: str = Field(default="", max_length=2000)

    _normalize_ids = field_validator("document_ids")(_copilot_document_ids)


class AssignmentProposal(StrictModel):
    tool: Activity
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=10000)
    objectives: list[str] = Field(min_length=1, max_length=8)
    rationale: str = Field(min_length=1, max_length=2000)
    config: dict

    @field_validator("objectives")
    @classmethod
    def objectives_are_measurable_text(cls, values):
        values = list(dict.fromkeys(" ".join(value.split()) for value in values))
        if any(not value or len(value) > 500 for value in values):
            raise ValueError("Provide concise learning objectives.")
        return values

    @model_validator(mode="after")
    def engine_schema_is_authoritative(self):
        config = CONFIG_MODELS[self.tool].model_validate(self.config, strict=True)
        if self.tool == "reflections":
            # Preserve the established topic/milestone authoring checks.
            ReflectionCopilotProposal(title=self.title, instructions=self.instructions,
                                      rationale=self.rationale, config=config)
        elif self.tool == "socratic":
            if not config.keywords or not config.prompt.strip() or config.learning_objective_id:
                raise ValueError("Propose keywords and a learning prompt, not an existing objective ID.")
        elif self.tool == "self-directed-learning":
            if not config.starting_point.strip() or not config.ending_point.strip() or not config.prompt.strip():
                raise ValueError("SDL needs a learning focus, starting point and ending point.")
            if config.learning_plan or config.custom_questions:
                raise ValueError("Generate and review the SDL lesson through the existing instructor workflow.")
        self.config = config.model_dump(mode="json")
        return self

    def assignment_input(self, course_id):
        # Objectives survive the normal save/reopen workflow without a new DB field.
        instructions = self.instructions + "\n\nLearning objectives:\n" + "\n".join(
            f"- {objective}" for objective in self.objectives)
        return AssignmentInput(course_id=course_id, tool=self.tool, title=self.title,
                               instructions=instructions, config=self.config)


class FinalOutput(StrictModel):
    proposal: AssignmentProposal
    source_ids: list[str] = Field(min_length=1, max_length=36)


class CopilotResponse(StrictModel):
    request_id: UUID
    proposal: AssignmentProposal
    evidence: list[ReflectionCopilotEvidence] = Field(min_length=1, max_length=36)
    warnings: list[str] = Field(default_factory=list)


class CourseToolInput(StrictModel):
    course_id: UUID


class MaterialQueryInput(StrictModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=4, ge=1, le=6, strict=True)


class SearchMaterialsInput(CourseToolInput, MaterialQueryInput):
    pass


class EmptyInput(StrictModel):
    pass


class ValidateDraftInput(StrictModel):
    draft: AssignmentProposal
