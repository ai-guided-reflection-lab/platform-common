"""Manifests describe existing contracts; they never grant engine access."""
from platform_app.schemas import CONFIG_MODELS

_DETAILS = {
    "socratic": dict(name="Socratic Chat", best_for=["conceptual understanding", "misconception diagnosis", "distinguishing concepts"],
                     required_fields=["document_ids", "keywords", "prompt"],
                     constraints=["At most eight keywords; instructor confirms keywords through the normal form."],
                     preview_kind="configuration", engine_endpoint="platform_app.engines._socratic_message"),
    "reflections": dict(name="Reflections", best_for=["metacognition", "reflection on applied experience", "milestone learning"],
                        required_fields=["document_ids", "module_type"],
                        constraints=["Topic mode needs topics and sub-topics.", "Milestone mode needs a prompt and manually attached historical CSV before publishing; never send CSV to the agent."],
                        preview_kind="configuration", engine_endpoint="PUT /internal/platform/modules/{assignment_id}"),
    "self-directed-learning": dict(name="Self Directed Learning", best_for=["objective coverage", "scaffolded independent learning", "diagnostic and practice progression"],
                                  required_fields=["document_ids", "prompt", "starting_point", "ending_point"],
                                  constraints=["The engine generates diagnostic, lesson and practice content only after the instructor selects Review activity."],
                                  preview_kind="generated_lesson", engine_endpoint="POST /api/platform/assignments/{assignment_id}/prepare-sdl"),
    "debate": dict(name="Debate", best_for=["argumentation", "evaluating evidence", "defending competing positions"],
                   required_fields=["document_ids", "scenario"],
                   constraints=["Include positions and evidence expectations in scenario; minimum_messages controls minimum student turns."],
                   preview_kind="configuration", engine_endpoint="platform_app.debate.generate_reply"),
    "aiducate": dict(name="AIducate", best_for=[], required_fields=[],
                     constraints=["Runtime contract is not finalized. Unavailable to the copilot."],
                     preview_kind=None, engine_endpoint=None),
}


def list_capabilities():
    result = []
    for key, details in _DETAILS.items():
        model = CONFIG_MODELS[key]
        result.append({"id": key, **details, "available": key != "aiducate",
                       "optional_fields": [field for field in model.model_fields if field not in details["required_fields"]],
                       "supports_documents": True, "supported_materials": ["indexed instructor-selected course documents"],
                       "supports_preview": key != "aiducate", "validation_function": f"{model.__name__}.model_validate",
                       "configuration_schema": model.model_json_schema(),
                       "engine_contract": {"start": "POST /api/platform/assignments/{assignment_id}/start",
                                           "message": "POST /api/platform/assignments/{assignment_id}/messages",
                                           "request_schema": "MessageInput", "access": "student engine only; never an authoring tool"} if key != "aiducate" else None,
                       "save_endpoint": "POST /api/platform/assignments (instructor only)",
                       "preview_endpoint": "Review activity in the existing form (instructor only)"})
    return result
