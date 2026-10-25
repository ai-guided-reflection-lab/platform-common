import json
import logging

from pydantic import ValidationError

logger = logging.getLogger("platform.copilot")
UNAVAILABLE = "The local Assignment Copilot is unavailable. Ask an administrator to check its model and connection, or continue configuring the assignment manually."


class ProposalConstraintError(ValueError):
    """Application-defined reason code, without model or course content."""


def audit_validation_failure(request_id, exc, *, schema, turn, repair_attempted, repair_available):
    # Only schema-defined field names may enter logs. Extra-key locations can
    # contain arbitrary model text, and exception messages/inputs can be private.
    fields = set()

    def collect(node):
        if isinstance(node, dict):
            fields.update(node.get("properties", {}))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(schema.model_json_schema())
    reason, issues = "invalid_structure", []
    if isinstance(exc, ValidationError):
        reason = "schema_validation"
        issues = [{"field": ".".join(str(part) if isinstance(part, int) or part in fields else "[extra]"
                                    for part in item["loc"]), "type": item["type"]}
                  for item in exc.errors(include_input=False, include_context=False, include_url=False)[:8]]
    elif isinstance(exc, json.JSONDecodeError):
        reason = "invalid_json"
    elif isinstance(exc, ProposalConstraintError):
        reason = str(exc)  # Constructed only from fixed application literals.
    elif isinstance(exc, KeyError):
        reason = "missing_field"
        issues = [{"field": exc.args[0] if exc.args[0] in fields else "[extra]", "type": "missing"}]
    logger.warning(json.dumps({"request_id": str(request_id), "event": "proposal_validation_failed",
                               "reason": reason, "issues": issues, "turn": turn,
                               "repair_attempted": repair_attempted, "repair_available": repair_available}))


def audit(request_id, event, *, tool=None, status=None):
    # Never include actor names, course text, queries, prompts or student content.
    logger.info(json.dumps({"request_id": str(request_id), "event": event,
                            "tool": tool, "status": status}))
