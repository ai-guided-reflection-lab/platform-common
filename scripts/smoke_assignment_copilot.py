"""Live local inference/tool smoke test with fixture retrieval; never a full-stack test.

Run from the repository root: .venv/bin/python scripts/smoke_assignment_copilot.py
No production documents, embeddings, student responses, or database writes.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_app.main import app as _gateway  # Initialize the gateway import path.
from app import settings
from platform_app import shared_rag
from platform_app.copilot.orchestrator import propose
from platform_app.copilot.schemas import CopilotRequest

PASSAGE = (
    "An operating system gives each process a separate virtual address space and resources. "
    "Threads within one process share its address space and resources but have their own stack "
    "and execution state. A failure in one process is usually isolated from other processes. "
    "Shared memory between threads requires synchronization to avoid races."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activity", choices=["socratic", "reflections", "self-directed-learning", "debate"])
    parser.add_argument("--timeout", type=int, default=180, help="Live inference budget, including cold model loading")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("timeout must be positive")
    course, document = str(uuid4()), str(uuid4())

    def retrieve(course_id, ids, query, limit):
        assert course_id == course and ids == [document]
        return {"chunks": [{"document_id": document, "text": PASSAGE}]}

    body = CopilotRequest(course_id=course, document_ids=[document],
        goal="Create an assignment that helps students distinguish processes from threads using the uploaded operating-systems materials.",
        current={"tool": args.activity} if args.activity else {})
    checks = []
    started = time.monotonic()
    with patch.object(shared_rag, "search", retrieve), patch.object(settings, "PLATFORM_AGENT_TIMEOUT_SECONDS", args.timeout):
        result = propose(body, {document: "Operating systems sample.txt"}, authorize=lambda: checks.append(True),
            course_context={"course_id": course, "title": "Operating Systems", "description": "Processes and threads."})
    assert result.proposal.assignment_input(course)
    if not args.activity:
        assert result.proposal.tool == "socratic", "The OS conceptual tracer should recommend Socratic Chat"
    print(json.dumps({"test": "live local model with fixture retrieval", "activity": result.proposal.tool,
        "title": result.proposal.title, "objectives": result.proposal.objectives,
        "sources": len(result.evidence), "authorization_checks": len(checks),
        "assignment_input_valid": True, "elapsed_seconds": round(time.monotonic() - started, 1)}))


if __name__ == "__main__":
    try:
        main()
    except HTTPException as exc:
        raise SystemExit(f"{exc.status_code}: {exc.detail}") from None
