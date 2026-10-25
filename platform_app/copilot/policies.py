import json
import logging

logger = logging.getLogger("platform.copilot")
UNAVAILABLE = "The local Assignment Copilot is unavailable. Ask an administrator to check its model and connection, or continue configuring the assignment manually."


def audit(request_id, event, *, tool=None, status=None):
    # Never include actor names, course text, queries, prompts or student content.
    logger.info(json.dumps({"request_id": str(request_id), "event": event,
                            "tool": tool, "status": status}))
