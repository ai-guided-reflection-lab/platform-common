"""Bounded read-only platform orchestration, with legacy Reflections compatibility."""
from __future__ import annotations

import json
import time

import httpx
from fastapi import HTTPException
from openai import APIError, OpenAI
from pydantic import Field, ValidationError

from app import settings
from platform_app.schemas import (ReflectionCopilotProposal, ReflectionCopilotResponse, StrictModel,
                                  ListSelectedDocumentsInput, SearchSelectedCourseMaterialsInput)
from . import provider
from .policies import UNAVAILABLE, audit
from .prompts import SYSTEM_POLICY, LEGACY_SYSTEM_POLICY
from .schemas import FinalOutput, CopilotResponse
from .tools import CourseTools, _SelectedMaterials, safe_title, _invalid, TOOLS


class _FinalOutput(StrictModel):
    proposal: ReflectionCopilotProposal
    source_ids: list[str] = Field(min_length=1, max_length=36)


LEGACY_TOOLS = [
    {"type": "function", "function": {"name": "list_selected_documents", "parameters": ListSelectedDocumentsInput.model_json_schema()}},
    {"type": "function", "function": {"name": "search_selected_course_materials", "parameters": SearchSelectedCourseMaterialsInput.model_json_schema()}},
]


def _legacy_response(content, body, materials):
    if not isinstance(content, str) or len(content) > 60000:
        raise ValueError("Invalid final response size")
    data = json.loads(content)
    # These fields are controlled by the application, never by model output.
    config = data["proposal"]["config"]
    config["document_ids"] = body.document_ids
    config["historical_data"] = ""
    final = _FinalOutput.model_validate(data)
    if final.proposal.config.module_type != body.current.module_type:
        raise ValueError("Keep the instructor's selected reflection mode")
    source_ids = list(dict.fromkeys(final.source_ids))
    if any(source_id not in materials.sources for source_id in source_ids):
        raise ValueError("Cite only retrieved source_ids")
    return ReflectionCopilotResponse(proposal=final.proposal, evidence=[materials.sources[key] for key in source_ids])



def _final_response(content, body, materials):
    if not isinstance(content, str) or len(content) > 60000:
        raise ValueError("Invalid final response size")
    if not materials.context_loaded or not materials.capabilities_loaded:
        raise ValueError("Load course context and capabilities before proposing")
    data = json.loads(content)
    config = data["proposal"]["config"]
    config["document_ids"] = body.document_ids
    if data["proposal"]["tool"] == "reflections":
        config["historical_data"] = ""
    final = FinalOutput.model_validate(data)
    materials.check_proposal(final.proposal)
    source_ids = list(dict.fromkeys(final.source_ids))
    if any(key not in materials.sources for key in source_ids):
        raise ValueError("Cite only retrieved sources")
    warnings = []
    if final.proposal.tool == "reflections" and config.get("module_type") == "milestone_based":
        warnings.append("Attach the historical CSV manually before publishing. Existing CSV stays in your form.")
    if final.proposal.tool == "self-directed-learning":
        warnings.append("Select Review activity to generate and check the lesson, diagnostic and practice before publishing.")
    return CopilotResponse(request_id=body.request_id, proposal=final.proposal,
                           evidence=[materials.sources[key] for key in source_ids], warnings=warnings)


def propose(body, documents, *, authorize=None, course_context=None, legacy=False, client_factory=None):
    """Caller supplies authorized names only; all retrieval rechecks course scope."""
    if set(documents) != set(body.document_ids):
        raise HTTPException(422, "Select indexed documents from this course only.")
    if not legacy and authorize is None:
        raise ValueError("Platform tools require a current course authorization callback")
    if authorize:
        authorize()
    names = {key: safe_title(documents[key]) for key in body.document_ids}
    materials = (_SelectedMaterials(body, names) if legacy else
                 CourseTools(body, names, authorize, course_context or {}))
    request_id = getattr(body, "request_id", None)
    audit(request_id, "proposal_started")
    deadline = time.monotonic() + max(1, settings.PLATFORM_AGENT_TIMEOUT_SECONDS)
    # Fixed dispatch: model strings never resolve attributes, HTTP routes or code.
    dispatch = {
        "list_selected_documents": materials.list_documents,
        "search_selected_course_materials": materials.search,
    }
    turns = min(4 if legacy else 8, max(1, settings.PLATFORM_AGENT_MAX_TOOL_TURNS))
    call_limit = min(6 if legacy else 10, max(1, settings.PLATFORM_AGENT_MAX_TOOL_CALLS))
    schema = _FinalOutput if legacy else FinalOutput
    policy = LEGACY_SYSTEM_POLICY if legacy else SYSTEM_POLICY
    messages = [
        {"role": "system", "content": policy + "\nFinal JSON schema:\n" + json.dumps(schema.model_json_schema())},
        {"role": "user", "content": json.dumps({
            "course_id": str(body.course_id),
            "goal": body.goal,
            "revision": getattr(body, "revision", ""),
            "current": body.current.model_dump(),
            "selected_document_count": len(documents),
        })},
    ]
    calls_used, repairing, argument_repairs_used = 0, False, 0
    try:
        local, model = provider.local_client(client_factory or OpenAI)
        with local as client:
            for turn in range(turns):
                tools_allowed = not repairing and turn < turns - 1 and calls_used < call_limit
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HTTPException(503, UNAVAILABLE)
                options = {"tools": LEGACY_TOOLS if legacy else TOOLS} if tools_allowed else {"response_format": {"type": "json_object"}}
                completion = client.chat.completions.create(
                    model=model, messages=messages, temperature=0.2, max_tokens=4000,
                    reasoning_effort="none", timeout=remaining, **options,
                )
                if not completion.choices or not completion.choices[0].message:
                    raise _invalid("returned an empty response.")
                message = completion.choices[0].message
                if time.monotonic() >= deadline:
                    raise HTTPException(503, UNAVAILABLE)
                tool_calls = message.tool_calls or []
                if tool_calls:
                    if not tools_allowed or calls_used + len(tool_calls) > call_limit:
                        raise _invalid("reached its tool-call limit.")
                    if any(call.type != "function" or not call.id or not call.function
                           or not isinstance(call.function.arguments, str) for call in tool_calls):
                        raise _invalid("returned an invalid tool call.")
                    if len({call.id for call in tool_calls}) != len(tool_calls):
                        raise _invalid("returned duplicate tool call identifiers.")
                    # Replay only the public message fields, excluding reasoning.
                    messages.append({"role": "assistant", "content": None, "tool_calls": [
                        {"id": call.id, "type": "function", "function": {
                            "name": call.function.name, "arguments": call.function.arguments,
                        }} for call in tool_calls
                    ]})
                    for call in tool_calls:
                        handler = dispatch.get(call.function.name) if legacy else lambda arguments: materials.dispatch(call.function.name, arguments)
                        if handler is None:
                            raise _invalid("requested an unsupported tool.")
                        try:
                            if len(call.function.arguments) > 40000:
                                raise ValueError("Tool arguments too large")
                            arguments = json.loads(call.function.arguments)
                            if authorize and legacy:
                                authorize()
                            result = handler(arguments)
                            audit(request_id, "tool_completed", tool=call.function.name, status="ok")
                        except ValidationError as exc:
                            if legacy or argument_repairs_used:
                                raise _invalid("supplied invalid tool arguments.") from exc
                            # One correction for a known tool; the rejected call
                            # has not executed retrieval or any other capability.
                            # Count it in the same budgets. Never echo raw inputs.
                            argument_repairs_used += 1
                            result = {"error": "invalid_arguments", "retry_remaining": 1,
                                      "issues": [{"field": ".".join(map(str, item["loc"])),
                                                  "type": item["type"]} for item in exc.errors()],
                                      "instruction": "Correct arguments to match this tool's schema. Search limit is 1 to 6."}
                            audit(request_id, "tool_rejected", tool=call.function.name, status="invalid_arguments")
                        except (ValueError, TypeError) as exc:
                            raise _invalid("supplied invalid tool arguments.") from exc
                        calls_used += 1
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
                    continue
                if not materials.sources:
                    raise _invalid("did not retrieve supporting course material.")
                try:
                    if authorize:
                        authorize()  # Revocation while inference was running takes effect.
                    result = (_legacy_response(message.content, body, materials) if legacy else
                              _final_response(message.content, body, materials))
                    audit(request_id, "proposal_completed", tool=getattr(result.proposal, "tool", "reflections"), status="ok")
                    return result
                except (ValueError, TypeError, KeyError, ValidationError) as exc:
                    if repairing or turn == turns - 1:
                        raise _invalid("could not produce a valid, grounded proposal.") from exc
                    repairing = True
                    # No tools on repair, no provider output or validation internals in logs.
                    messages.append({"role": "assistant", "content": (message.content or "")[:16000]})
                    feedback = {"instruction": "Repair the final JSON to match the schema. Return JSON only. Do not call tools.",
                                "allowed_source_ids": list(materials.sources),
                                "requested_mode": body.current.module_type}
                    if not legacy:
                        feedback["requested_activity"] = body.current.tool
                    if isinstance(exc, ValidationError):
                        feedback["issues"] = [{"field": ".".join(map(str, item["loc"])),
                                               "type": item["type"], "message": item["msg"][:200]}
                                              for item in exc.errors()[:8]]
                    else:
                        feedback["issues"] = [{"type": "invalid_json_or_policy_constraint"}]
                    messages.append({"role": "user", "content": json.dumps(feedback)})
    except HTTPException as exc:
        audit(request_id, "proposal_failed", status=exc.status_code)
        raise
    except (APIError, httpx.HTTPError, ValueError) as exc:
        audit(request_id, "proposal_failed", status=503)
        raise HTTPException(503, UNAVAILABLE) from exc
    raise _invalid("reached its model-turn limit.")
