# Instructor Assignment Copilot verification

Checked locally on October 25, 2026. The [current plan](../PLAN.md) preserves Reflections as the first delivery slice within the original platform-wide architecture.

| Check | Result | Evidence and limits |
| --- | --- | --- |
| Shared/legacy agent unit and HTTP security tests | PASS | 72 tests; local inference and retrieval mocked. Includes tool allowlist, strict arguments, one bounded argument correction, budgets, one JSON repair, authorization on every tool/final response, prompt-injection containment, server-derived citations, provider isolation, safe failures and audit privacy. |
| Real PostgreSQL course/assignment integration | PASS | 28 tests in throwaway schemas in a temporary localhost pgvector container. Covers proposal loop → explicit instructor save → reopen for Reflections, Socratic, SDL and Debate; inference/retrieval mocked. Proposal generation leaves assignment rows unchanged. |
| Student provider compatibility | PASS | Socratic settings: 6 tests; Reflections provider errors/role precedence: 4 tests; SDL configuration: 5 tests. Additional provider subtests pass. |
| Copilot/create-activity/Reflections frontend | PASS | 46 tests. Includes recommendation, explicit/individual apply, revisions, stale responses, retained milestone CSV, editable Socratic and Debate controls, and no save before instructor action. |
| Production frontend build | PASS | Vite builds all three existing entry points. |
| Live Qwen automatic activity selection | PASS | Installed Qwen weights, using the 16K-context `courselab-copilot` alias, recommended Socratic Chat for the OS processes/threads goal and returned objectives, rationale, valid AssignmentInput and one fixture passage; the corrected live run took 39.4 seconds. Retrieval/auth used controlled fixtures, with no database or embedding provider. |
| Live Qwen Reflections proposal | PASS | The same Qwen weights, using the supplied 16K-context `courselab-copilot` alias, respected selected Reflections and produced valid topic configuration with objectives and fixture evidence; the corrected live run took 68.8 seconds. Smoke harness allows a 180-second cold-load budget; this does not prove every request finishes within the normal 60-second setting. |
| Full browser with live model and real document retrieval | NOT RUN | Follow the manual flow below. Independent model, database and component checks do not establish this combined path. |
| Hosted / Canvas / student-engine pedagogical quality | NOT RUN | No deployment or publication performed. AIducate remains unavailable to the agent. |

Broader regression runs are **not fully green**. The frontend suite reports **92 passed, 2 failed**: `instructor-summary.test.jsx` expects the old “Activity title” label, and `lesson-preview.test.jsx` expects the old “Correct option (1–4)” control. Debate lifecycle tests report **1 passed, 2 failed**: the current native message branch omits sources and a test uses a non-course document before mocking ownership. Both pairs reproduce against unchanged commit `397220c` in a temporary copy. These existing student-engine/test issues were not changed as part of copilot authoring.

Repeat live runs exposed two issues: the running Ollama model had a 4,096-token context (confirmed via `/api/ps`), which truncated the shared registry and sometimes lost the selected activity; the private local configuration also retained the earlier four-turn/six-call budgets. Use the supplied 16K-context `courselab-copilot` alias and six-turn/eight-call budgets. No Qwen weights are redownloaded. The private local `.env` now uses this alias, six turns, eight calls and a 180-second authoring timeout; URLs and student-provider settings were preserved. Restart the gateway to load the updated local settings. One run also requested a search limit of 10 despite the schema maximum of six. It safely returned 502 without retrieval. The current policy states the limit explicitly and permits one strict, bounded correction for known-tool argument errors; regression tests verify that invalid arguments never execute retrieval and repeated violations terminate. A local model can still fail to propose, so manual configuration remains available.

## Reproduce automated checks

Use a dedicated disposable PostgreSQL/pgvector database. `TEST_DATABASE_URL` tests create and drop unique schemas; do not point them at a production course database.

```sh
PIPELINE_TRACE_FILE= .venv/bin/python -m pytest -q \
  platform_unit_tests/test_assignment_copilot.py \
  platform_unit_tests/test_reflection_copilot.py

# Export TEST_DATABASE_URL privately for an isolated pgvector database first.
PIPELINE_TRACE_FILE= .venv/bin/python -m pytest -q \
  platform_tests/test_assignment_copilot.py \
  platform_tests/test_reflection_copilot.py \
  platform_tests/test_assignments.py

PYTHONPATH=Socratic-Chat/backend .venv/bin/python -m pytest -q Socratic-Chat/backend/tests/test_settings.py
PYTHONPATH=reflections-app/backend .venv/bin/python -m pytest -q reflections-app/backend/tests/test_provider_errors.py
PYTHONPATH=adaptive-learning-app/backend .venv/bin/python -m pytest -q adaptive-learning-app/backend/tests/test_database_config.py

cd platform_frontend
npm test -- src/assignment-copilot.test.jsx src/create-activity.test.jsx src/reflection-copilot.test.jsx src/reflections.test.jsx
npm run build
cd ..
git diff --check
```

## Reproduce live inference smoke checks

Configure the local model using [README setup](../README.md#instructor-assignment-copilot). The script uses a built-in OS passage and fixture authorization/retrieval. It performs no course reads, embedding calls, assignment writes or publication.

```sh
PLATFORM_AGENT_MODEL=courselab-copilot PLATFORM_AGENT_MAX_TOOL_TURNS=6 PLATFORM_AGENT_MAX_TOOL_CALLS=8 \
  PLATFORM_AGENT_BASE_URL=http://127.0.0.1:11434/v1 PIPELINE_TRACE_FILE= \
  .venv/bin/python scripts/smoke_assignment_copilot.py
PLATFORM_AGENT_MODEL=courselab-copilot PLATFORM_AGENT_MAX_TOOL_TURNS=6 PLATFORM_AGENT_MAX_TOOL_CALLS=8 \
  PLATFORM_AGENT_BASE_URL=http://127.0.0.1:11434/v1 PIPELINE_TRACE_FILE= \
  .venv/bin/python scripts/smoke_assignment_copilot.py --activity reflections
```

Expected: automatic selection reports `socratic`; fixed selection reports `reflections`; both report `assignment_input_valid: true`, objectives and at least one source. The script uses a 180-second model-loading budget by default; `--timeout 60` checks the normal configured budget separately.

## Manual test: combined browser and real retrieval

For the generic “could not produce a valid, grounded proposal” error, restart or
reload the gateway after updating its code, retry once, and search gateway logs
for `proposal_validation_failed` with the `request_id` from the browser's
`/platform/copilot/propose` payload. Warning-level events identify invalid JSON,
schema validation, missing context/capabilities, or a proposal policy constraint
(such as `unretrieved_source_ids` or `selected_activity_mismatch`). Schema issues
include field paths and error types; unknown field names are redacted. Each event
records the one-based model turn, whether this was the repair attempt, and
whether another repair is available. A failed first draft can still be repaired
successfully, so correlate the request's final outcome. No prompts, model output,
validation input values, or document text are logged. These diagnostics do not
relax proposal validation or establish the cause of an earlier request.

For “supplied invalid tool arguments”, search for warning-level
`tool_arguments_rejected` events. They include the allowlisted tool name,
redacted schema field paths and error types, request ID, model turn, attempted
call count, and correction availability/status. Malformed JSON and oversized
arguments are identified separately. `proposal_failed` is also warning-level so
terminal failures remain visible when INFO audit events are filtered out. No
argument values or exception messages are logged. The targeted shared/legacy
unit suite passes 84 tests, including repeated rejection and log privacy checks.

The live retry identified `get_course_context` rejecting `course_id` with
`uuid_parsing`, followed by a cross-course 403 on the model's corrected call.
Course-scoped tool schemas now omit `course_id`; dispatch supplies it from the
authorized request. Explicit conflicting IDs still fail the existing scope
guard, and authorization still runs for every call. The shared/legacy unit suite
passes 87 tests after this change, including scoped retrieval without a model
course ID, argument immutability, and explicit cross-course rejection. A fresh
Canvas proposal with real inference/retrieval still requires a live retry.

Prerequisites: gateway, PostgreSQL/pgvector and SDL document service running; correct document-service token and embedding configuration; local Ollama model reachable; a professor managing a test course with indexed, instructor-approved materials. Use a disposable course. Student conversations remain independent.

1. Open Create New Activity, select indexed OS materials and leave the activity unselected.
2. Enter: “Create a Socratic assignment that helps students distinguish processes from threads using the uploaded operating-systems materials.” Prepare a proposal.
3. Confirm the recommendation is Socratic Chat, objectives are measurable, the rationale explains conceptual questioning, and every source is from the selected course materials. Confirm title/configuration have not changed.
4. Apply the proposal. Confirm title, description/objectives, keywords, opening prompt and minimum-message settings populate normal editable controls. Edit one field. Confirm applying alone sends no assignment-save or publish request.
5. Save draft explicitly, reopen it and confirm values persist. Do not publish as part of this test.
6. Repeat with Reflections selected. Confirm topics, ordered sub-topics, depth, probing, application and notes remain editable. For milestone mode attach a test CSV; verify it never appears in copilot requests and remains attached after applying.
7. Apply an individual title or objective field and confirm other settings stay unchanged. Request a revision and confirm the goal/revision use the same selected documents. Change goal/materials/mode while inference runs; confirm late or stale proposals cannot apply.
8. Stop or disable local inference. Confirm a safe unavailable message and that manual configuration/save remain usable; restart it for a subsequent proposal.
9. For SDL, confirm the copilot proposes focus/start/end only. The instructor's existing Review activity generates the diagnostic, lesson and practice. For Debate, confirm scenario, opening prompt and minimum-message settings remain editable. AIducate must not be proposed.

Record PASS/FAIL for this combined flow separately from the automated and fixture-based checks above.
