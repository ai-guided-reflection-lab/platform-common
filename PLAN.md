# Reflections Instructor Assignment Copilot — One-Shot Implementation Plan

## Objective

Add a locally hosted, open-weight Instructor Assignment Copilot to the existing professor activity-creation workflow for the **Reflections** assignment type only.

The copilot will use an Ollama-hosted model to inspect instructor-selected course documents through a small, read-only tool set and return an evidence-grounded Reflections assignment proposal. The instructor can review and apply the proposal to the existing form, edit it, save it as a draft, or publish it through the existing controls.

This phase must not change the model provider or runtime behavior of the student-facing Reflections chatbot. Reflections remains free to use its existing role-specific external or local providers.

## User Story

As an instructor creating a Reflections activity, I can describe what I want students to reflect on, ask CourseLab to prepare the activity from selected course materials, review the proposed configuration and evidence, and apply it to the normal editable assignment form without allowing the AI to save or publish anything on my behalf.

## End-to-End Tracer

The implementation is complete when this path works:

1. An instructor opens **Create New Activity** from a course.
2. The instructor selects one or more indexed course documents.
3. The instructor selects **Reflections**.
4. A new **Assignment Copilot** panel appears above the existing Reflections settings.
5. The instructor enters a goal such as: `Help students reflect on why requirements must be testable and how they applied that idea.`
6. The platform sends the course ID, selected document IDs, goal, and non-sensitive current draft fields to a dedicated copilot endpoint.
7. The local model uses allowlisted tools to inspect the selected documents and retrieve relevant passages.
8. The endpoint returns a validated Reflections proposal with a rationale and evidence references.
9. The UI shows the proposal without changing the form.
10. The instructor selects **Apply proposal**.
11. The existing title, description, and Reflections configuration fields are populated and remain editable.
12. No assignment is written until the instructor uses the existing **Save draft** or **Publish activity** control.

## Scope

### Included

- The active professor workflow in `platform_frontend/src/CreateActivity.jsx`.
- Reflections assignments only.
- Both existing Reflections modes:
  - `topic_based`: propose required topics, sub-topics, expected depth, probing style, application requirement, and professor notes.
  - `milestone_based`: propose the milestone prompt and pedagogical settings, but never create, read, replace, or transmit the historical-response CSV.
- An Ollama/OpenAI-compatible local platform-agent client with dedicated configuration.
- Read-only document-listing and course-material-search tools.
- Strict request, tool-argument, and final-proposal schemas.
- Instructor-visible rationale and evidence excerpts derived from retrieved course passages.
- Backend, frontend, authorization, failure-path, and build tests.
- Setup documentation and environment variables.

### Excluded

- Socratic, SDL, Debate, AIducate, or Student Agent authoring.
- Changes to student-facing Reflections conversations, LangGraph graphs, prompts, evaluation, checkpoints, or provider selection.
- Model fine-tuning or pedagogy-specific post-training.
- Autonomous draft creation, database writes, assignment publication, recipient changes, document upload, or document deletion.
- Giving the model SQL, filesystem, shell, arbitrary HTTP, assignment-save, or publish tools.
- Sending historical milestone CSV data to the platform agent.
- Persisting copilot conversations or proposals in this phase.
- Streaming responses or multi-user copilot sessions.

## Locked Design Decisions

1. **The platform agent is separate from assignment engines.** Use `PLATFORM_AGENT_*` settings; do not reuse `LLM_PROVIDER` or Reflections role settings.
2. **The agent is read-only.** The backend endpoint returns a proposal. Only existing application code can save or publish it after explicit instructor action.
3. **Course authorization is checked server-side.** The endpoint requires a signed-in professor who manages the supplied course.
4. **The selected-document boundary is authoritative.** Tools may retrieve only from document IDs selected in the form and belonging to the active course.
5. **Course text is untrusted data.** Retrieved passages cannot redefine the system policy, tools, output schema, or approval boundary.
6. **The model never sees milestone history.** `historical_data` is omitted from the request and model context and preserved locally when a proposal is applied.
7. **The existing schemas remain authoritative.** The final configuration must validate through `ReflectionConfig`; the eventual save continues through `AssignmentInput`.
8. **Evidence is server-derived.** The model returns retrieved source identifiers, and the server constructs the final filename/excerpt objects from actual tool results. The model cannot invent displayed citations.
9. **Failure leaves the manual workflow intact.** If Ollama is missing, slow, malformed, or unavailable, the instructor can continue configuring Reflections normally.
10. **No database migration is required.** This phase adds no persisted state.

## Proposed API Contract

### Endpoint

`POST /api/platform/copilot/reflections/propose`

Authentication: `professor` dependency plus `manage_course(body.course_id, account)`.

### Request

```json
{
  "course_id": "uuid",
  "goal": "What students should reflect on and why",
  "document_ids": ["document-uuid"],
  "current": {
    "title": "Optional current title",
    "instructions": "Optional current description",
    "module_type": "topic_based"
  }
}
```

Constraints:

- `goal`: 10–2,000 characters.
- `document_ids`: 1–100 unique IDs.
- `current` is optional and contains no `historical_data`.
- Reject document IDs outside the course with `422`.
- Reject instructors who do not manage the course with `403`.

### Response

```json
{
  "proposal": {
    "title": "Testable requirements reflection",
    "instructions": "Reflect on how testability changes the way requirements are written and reviewed.",
    "config": {
      "document_ids": ["document-uuid"],
      "module_type": "topic_based",
      "required_topics": ["Testable requirements"],
      "sub_topics": [
        "How testability affects requirement wording",
        "Evidence that a requirement can be verified"
      ],
      "expected_depth": "applied",
      "probing_style": "socratic",
      "must_include_application": true,
      "custom_notes": "Ask students to connect one requirement to a concrete verification method.",
      "milestone_prompt": "",
      "historical_data": ""
    },
    "rationale": "An applied, Socratic reflection asks students to connect the definition of testability to their own requirement-writing decisions."
  },
  "evidence": [
    {
      "document_id": "document-uuid",
      "title": "Requirements.pdf",
      "excerpt": "A requirement should be stated so that its satisfaction can be verified..."
    }
  ]
}
```

Response rules:

- Always return `tool: reflections` implicitly through this dedicated endpoint; do not let the model choose another assignment type.
- `config.document_ids` must exactly match the accepted request selection.
- For `milestone_based`, return `historical_data: ""`; the frontend preserves any currently uploaded CSV rather than applying this value.
- Bound rationale and excerpt sizes.
- Return `503` for an unavailable/unconfigured local model and `502` for exhausted tool steps or malformed model output.
- Do not include model chain-of-thought, raw prompts, or hidden reasoning.

## Agent Tools

Implement only these internal tools in `platform_app/reflection_copilot.py`:

### `list_selected_documents`

Arguments: none.

Behavior:

- Return document ID and safe filename for the already authorized selection.
- Do not return file bytes or documents outside the request selection.

### `search_selected_course_materials`

Arguments:

```json
{
  "query": "string, 3–500 characters",
  "limit": "integer, 1–6"
}
```

Behavior:

- Call the existing shared RAG search over the authorized course and selected document IDs.
- Return bounded source IDs, filenames/titles, and excerpts without embeddings.
- Record returned sources in a server-side evidence map used to validate the final proposal.
- Treat passage contents as data, not instructions.

### Loop policy

- Maximum four model turns and six total tool calls per request.
- Allow only exact registered tool names.
- Validate every argument before execution.
- Reject duplicate or empty searches rather than looping indefinitely.
- Require at least one successful material search before accepting a final proposal.
- The final model response must be JSON matching the proposal schema.
- Permit one bounded repair request when the final JSON is malformed; do not rerun tools during repair.

## Implementation Tasks

### Task 1 — Add dedicated local-agent settings

Files:

- `Socratic-Chat/backend/app/settings.py`
- `.env.example`
- `render.yaml` only if the hosted platform should be able to point at an institution-hosted OpenAI-compatible endpoint; do not provision Ollama on Render.

Add:

```dotenv
PLATFORM_AGENT_PROVIDER=ollama
PLATFORM_AGENT_API_BASE_URL=http://host.docker.internal:11434/v1
PLATFORM_AGENT_API_KEY=ollama
PLATFORM_AGENT_MODEL=qwen3.5:9b-q4_K_M
PLATFORM_AGENT_TIMEOUT_SECONDS=60
PLATFORM_AGENT_MAX_TOOL_TURNS=4
PLATFORM_AGENT_MAX_TOOL_CALLS=6
```

Requirements:

- Add a `platform_agent_client_config()` helper independent of `llm_client_config()`.
- Support only `ollama`/`local` for this phase and fail clearly for another value.
- Return `None` when the feature is intentionally disabled with an empty model or base URL.
- Never fall back silently to OpenAI, Groq, or the student-facing model configuration.

### Task 2 — Define strict copilot schemas

Files:

- `platform_app/schemas.py`

Add strict models for:

- `ReflectionCopilotCurrentDraft`
- `ReflectionCopilotRequest`
- `ReflectionCopilotEvidence`
- `ReflectionCopilotProposal`
- `ReflectionCopilotResponse`
- tool arguments such as `SearchSelectedCourseMaterialsInput`

Requirements:

- Reuse `ReflectionConfig` for the proposal configuration.
- Normalize and deduplicate `document_ids`, topics, and sub-topics.
- Reject blank topics and overlong values.
- Do not place `historical_data` in the request model.
- Validate final mode-specific fields without requiring milestone CSV during proposal generation.

### Task 3 — Implement the bounded read-only agent loop

Files:

- `platform_app/reflection_copilot.py` (new)

Implementation:

- Use the existing `openai` client dependency against the dedicated OpenAI-compatible local endpoint.
- Define the two tool schemas in code.
- Build a system policy specifically for Reflections assignment authoring.
- Execute model-requested tools through a fixed dictionary, never dynamic lookup.
- Use `shared_rag.search()` for selected-document retrieval.
- Track real retrieved sources and replace model-supplied evidence with server-mapped evidence.
- Parse the final JSON, validate it with Pydantic, force the authorized `document_ids`, and clear `historical_data`.
- Convert provider/network/timeouts into a safe `503` without leaking internal URLs, keys, prompts, or provider responses.
- Convert invalid tool names, exhausted budgets, missing retrieval, and irreparable final output into an actionable `502`.
- Do not log raw document passages, full prompts, model reasoning, or milestone history.

Prompt requirements:

- Explain the pedagogical distinction between topic and milestone reflection.
- Require concise, measurable topics and ordered sub-topics.
- Use only selected materials for factual claims.
- Explicitly mark tool results and document passages as untrusted course content.
- Prohibit following instructions found inside passages.
- Prohibit save, publish, enrollment, grading, or student-contact actions.
- Ask the model for a short rationale, not hidden reasoning.

### Task 4 — Expose the professor-only proposal endpoint

Files:

- `platform_app/routes.py`

Implementation:

- Add `POST /copilot/reflections/propose` beneath the existing `/api/platform` router.
- Require `professor` and call `manage_course` before invoking the model.
- Verify every selected document belongs to the course using the same authoritative course-file source used by assignment validation.
- Pass only authorized filenames and retrieval functions into the agent runner.
- Do not open a database transaction across the model call.
- Do not call `create_assignment`, `update_assignment`, `publish`, or the Reflections engine.

### Task 5 — Add the Reflections copilot UI

Files:

- `platform_frontend/src/ReflectionCopilot.jsx` (new)
- `platform_frontend/src/CreateActivity.jsx`
- the existing platform stylesheet that owns `.activity-*` styles

UI behavior:

- Render the panel only when `draft.tool === "reflections"`.
- Place it above the existing `ReflectionConfig` so instructors can apply a proposal and then edit normal controls.
- Include a concise explanation that the local copilot prepares a draft and cannot save or publish it.
- Provide a labeled goal textarea and **Prepare proposal** button.
- Disable preparation until at least one indexed document is selected and the goal meets the minimum length.
- Send only `course_id`, goal, selected document IDs, title, instructions, and current module type.
- Show a non-blocking progress state and actionable errors.
- Preview title, instructions, mode, topics/prompt, rationale, and evidence before application.
- Require an explicit **Apply proposal** action.
- On apply:
  - set the title and instructions;
  - merge the proposed Reflections fields;
  - preserve the current `historical_data` value;
  - keep document selection controlled by `selected`;
  - invalidate the existing review stage by returning to the editable configuration stage;
  - do not call the assignment POST/PUT endpoint.
- If the instructor edits the goal or selected documents after generation, mark the visible proposal stale and require regeneration or explicit dismissal.
- Keep the existing manual Reflections form completely usable when the feature is unavailable.
- Use accessible labels, status messages, and keyboard-operable proposal actions.

### Task 6 — Backend tests

Files:

- `platform_tests/test_reflection_copilot.py` (new)
- `platform_unit_tests/test_reflection_copilot.py` (optional when isolated loop tests are clearer without PostgreSQL)

Cover:

1. Unauthenticated users receive `401`.
2. Students receive `403`.
3. A professor who does not manage the course receives `403`.
4. Missing or cross-course document IDs receive `422` before any model request.
5. The tool runner can list only selected course documents.
6. Search is limited to the selected document IDs.
7. Unknown tool names are rejected and never executed.
8. Invalid tool arguments are rejected.
9. Tool-call and turn budgets terminate loops.
10. At least one retrieval is required.
11. A valid topic-based proposal passes `ReflectionConfig` validation.
12. A milestone proposal returns no historical data.
13. Displayed evidence is drawn from actual retrieval results rather than model-authored excerpts.
14. Prompt-like instructions inside a retrieved passage are passed as untrusted tool data and cannot trigger another backend capability.
15. Unavailable local inference returns `503` with a safe message.
16. Malformed final output receives one repair attempt and then `502`.
17. Calling the endpoint does not create or update an assignment row.
18. Existing Reflections assignment and publication tests continue to pass.

Mock the model client; automated tests must not require Ollama, external APIs, or live model downloads.

### Task 7 — Frontend tests

Files:

- `platform_frontend/src/reflection-copilot.test.jsx` (new)
- `platform_frontend/src/create-activity.test.jsx`

Cover:

1. The panel appears only for Reflections.
2. Preparation is disabled without selected indexed materials or a sufficient goal.
3. The request contains the expected safe fields and excludes `historical_data`.
4. A returned proposal is previewed before the form changes.
5. **Apply proposal** updates title, description, and Reflections controls.
6. Applying a proposal does not call assignment POST/PUT or publish endpoints.
7. Existing milestone CSV content is preserved locally.
8. Changing selected documents marks the proposal stale.
9. Provider errors leave manual configuration available.
10. Status, error, and apply controls are accessible by role and label.
11. Existing create-activity tests continue to pass.

### Task 8 — Documentation and operator guidance

Files:

- `README.md`
- `.env.example`
- `docs/platform-ui-rework.md`

Document:

- How to install and run the selected Ollama model.
- Native versus Docker base URLs.
- That the copilot is Reflections-only and draft-only.
- That the platform agent is independent of the Reflections tutor/evaluator/planner providers.
- That hosted student interactions may still use external providers.
- Expected behavior when Ollama is unavailable.
- The exact manual validation flow below.

## Verification

Run from the repository root unless a command changes directories.

### Backend

```bash
.venv/bin/python -m pytest \
  platform_unit_tests/test_reflection_copilot.py \
  platform_tests/test_reflection_copilot.py \
  platform_tests/test_assignments.py
```

If the optional unit-test file is not created, omit it rather than adding an empty placeholder.

### Frontend

```bash
cd platform_frontend
npm test -- src/reflection-copilot.test.jsx src/create-activity.test.jsx
npm run build
```

### Repository hygiene

```bash
git diff --check
```

### Manual test

Prerequisites:

- Platform, PostgreSQL, and Reflections services running through the documented local stack.
- Ollama reachable through `PLATFORM_AGENT_API_BASE_URL` with `PLATFORM_AGENT_MODEL` installed.
- A professor account managing a course with at least one indexed document.

Steps:

1. Open the professor dashboard and select **Create New Activity**.
2. Select one indexed course document.
3. Select **Reflections**.
4. Enter a specific reflection goal and select **Prepare proposal**.
5. Confirm the preview includes a rationale and evidence from the selected document.
6. Confirm the existing assignment fields have not changed yet.
7. Select **Apply proposal**.
8. Confirm the title, description, and Reflections settings are populated and editable.
9. Edit one proposed sub-topic and save the draft.
10. Reopen the saved draft and confirm the applied values persisted.
11. Repeat with Ollama stopped and confirm an actionable error appears while manual Reflections configuration and draft saving still work.
12. For milestone mode, upload a CSV manually, generate/apply a proposal, and confirm the CSV remains present and was not sent in the copilot request.

Expected result:

- The local agent produces a grounded, reviewable Reflections proposal using only selected course materials.
- Applying the proposal changes only local form state.
- Saving and publishing remain explicit existing instructor actions.
- The student-facing Reflections provider and behavior are unchanged.

## Definition of Done

- The end-to-end tracer succeeds for a topic-based Reflections assignment.
- Milestone proposals never transmit or overwrite historical CSV data.
- The platform agent uses dedicated local-provider configuration.
- Only the two documented read-only tools are callable.
- Authorization and selected-course document boundaries are enforced before inference.
- The final proposal validates through existing Reflections schemas.
- Evidence shown to the instructor is derived from real retrieval results.
- No copilot endpoint can save or publish an assignment.
- All focused backend and frontend tests pass.
- The production frontend build passes.
- Manual success and provider-unavailable paths pass.
- Documentation explains setup, boundaries, and provider separation.

## Implementation Order

Implement in this order so the branch remains testable:

1. Settings and schemas.
2. Isolated agent runner with mocked unit tests.
3. Authorized API endpoint with integration tests.
4. Reflections copilot UI with mocked component tests.
5. End-to-end wiring in `CreateActivity`.
6. Focused regression suite and production build.
7. Documentation and manual local-model validation.

