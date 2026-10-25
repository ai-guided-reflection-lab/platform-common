# Instructor Assignment Copilot — platform-wide implementation plan

## Goal and sequence

Build a local open-weight platform agent that understands instructor learning outcomes, retrieves approved course materials, recommends an activity, constructs and validates its configuration, explains its rationale and sources, and returns a reviewable proposal. Instructors apply, edit, save and publish through the existing form.

**Reflections is the first end-to-end delivery slice, not the architectural scope limit.** Preserve the working Reflections implementation and its topic/milestone behavior. The next tracer restores the original Socratic OS example; subsequent activity support uses the same foundation. The historical Reflections-only task plan is retained in [docs/reflections-copilot-initial-plan.md](docs/reflections-copilot-initial-plan.md).

## Architectural boundary

```text
Local Platform Agent (platform_app/copilot/)
  course context and document retrieval
  capability-based activity recommendation
  strict structured tool calling
  proposal construction and AssignmentInput validation
  reviewable objectives, settings, rationale and sources

Assignment Engines (independent student interaction)
  Socratic     -> its configured provider and existing pipeline
  Reflections  -> its tutor/planner/evaluator providers
  SDL          -> its configured provider and lesson flow
  Debate       -> its configured provider and conversation
  AIducate     -> deferred until its runtime contract is finalized
```

The platform agent never joins normal student conversations. It has no save, publish, engine, SQL, arbitrary HTTP, filesystem or shell tools. Preview and lesson generation use the existing instructor review controls; the model cannot invoke those controls.

## Phase 1 — Preserve the Reflections vertical slice

Continue supporting topic-based proposals (objectives, topics, sub-topics, depth, probing and application) and milestone proposals (prompt and pedagogical settings). Never send historical CSV or student responses to the agent. Preserve attached CSV when applying settings, including when returning to a previously configured Reflections form.

Tracer: selected indexed materials → reflection outcome → local proposal → visible rationale and sources → explicit apply → edit normal controls → instructor saves draft → reopen unchanged draft.

Gate: authorization, privacy, stale proposals, schema validation, safe unavailability and save/reopen regression checks pass. A live local-model check is distinct from a full browser/real-retrieval end-to-end check.

## Phase 2 — Shared agent foundation and security

Use the dedicated `platform_app/copilot/` modules:

- `provider.py`: local Ollama/OpenAI-compatible client, no external fallback.
- `tools.py`: fixed registry and course-scoped retrieval; strict Pydantic arguments.
- `orchestrator.py`: bounded calls/turns, one repair, required retrieval and validation.
- `prompts.py`: general activity policy and legacy Reflections compatibility policy.
- `policies.py`: privacy-safe request-ID audit events and safe fallback messages.
- `schemas.py`: request/proposal contracts, measurable objectives and authoritative AssignmentInput validation.
- `capabilities.py`: manifests derived from existing engine schemas.

`POST /api/platform/copilot/propose` requires an authenticated course instructor. Recheck current instructor membership and selected-document ownership on every tool and before returning a proposal. Do not hold a database transaction across inference. Course titles, file names and passages are untrusted data, never executable instructions. Display citations only from server-recorded retrieval results.

Configuration:

```dotenv
PLATFORM_AGENT_PROVIDER=ollama
PLATFORM_AGENT_MODEL=qwen3.5:9b-q4_K_M
PLATFORM_AGENT_BASE_URL=http://host.docker.internal:11434/v1
PLATFORM_AGENT_API_KEY=ollama
PLATFORM_AGENT_TIMEOUT_SECONDS=60
PLATFORM_AGENT_MAX_TOOL_TURNS=6
PLATFORM_AGENT_MAX_TOOL_CALLS=8
SOCRATIC_LLM_PROVIDER=
REFLECTIONS_TUTOR_LLM_PROVIDER=
REFLECTIONS_PLANNER_LLM_PROVIDER=
REFLECTIONS_EVALUATOR_LLM_PROVIDER=
SDL_LLM_PROVIDER=
DEBATE_LLM_PROVIDER=
```

Empty student overrides preserve prior behavior. The legacy `PLATFORM_AGENT_API_BASE_URL` and Reflections `TUTOR_LLM_PROVIDER`/other role settings remain supported. Native gateway URLs use `http://127.0.0.1:11434/v1`. Run Ollama with a context of at least 16,384 tokens, or create the `courselab-copilot` alias from `scripts/ollama-copilot.Modelfile` and select it as the platform model; it reuses the Qwen weights. Agent budgets have hard ceilings of eight model turns and ten tool calls; the legacy Reflections endpoint retains its four-turn/six-call ceilings. One final-JSON repair and one correction of invalid arguments to a known tool share the same overall budgets; rejected arguments never execute a capability. Unknown tools and authorization failures fail immediately. Provider retries are disabled. A request ID correlates each proposal and audit event. There are no server-side agent mutations to replay; the UI applies each individual proposal field at most once. Assignment persistence remains the existing instructor-initiated endpoint.

## Phase 3 — Capabilities and the original Socratic tracer

Expose `get_course_context(course_id)`, `search_course_materials(course_id, query)`, `list_activity_capabilities()` and `validate_assignment_draft(draft)` as read-only tools. `applyAssignmentProposal` is the frontend equivalent of `apply_assignment_proposal`: it changes local form state after an instructor click and never calls persistence APIs.

Each capability supplies appropriate learning objectives, required/optional fields, supported materials, constraints, preview kind, configuration schema/validator and engine contract. Existing typed models in `platform_app/schemas.py` stay authoritative. AIducate is listed as unavailable and cannot be proposed.

Original tracer: “Create a Socratic assignment that helps students distinguish processes from threads using the uploaded operating-systems materials.”

1. Load authorized course context.
2. Inspect capabilities and retrieve selected approved OS materials.
3. Recommend Socratic Chat with a concise pedagogical rationale.
4. Propose measurable objectives, instructions, keywords, learning prompt and minimum messages supported by SocraticConfig.
5. Validate through SocraticConfig and AssignmentInput; never invent unsupported settings.
6. Display activity choice, objectives, configuration and real retrieved sources.
7. Apply the proposal to normal editable controls and invalidate any previous review/keyword preparation.
8. Let the instructor confirm keywords, edit and save through the existing draft workflow.

Acceptance: no direct agent database access; every document is selected and belongs to the active course; valid AssignmentInput; no assignment changes before explicit save; publish is never a model tool.

## Phase 4 — Shared copilot UI

Place the panel in Create New Activity after materials, before manual activity selection. With no activity chosen, recommend one. With an activity chosen, preserve that instructor selection. The regular form stays available.

Support complete apply, individual title/instructions/objectives/settings apply, revision and dismiss. Show activity choice, rationale, objectives, selected-material excerpts, configuration, warnings and missing manual prerequisites. Mark proposals stale when course, goal, documents, selected activity or reflection mode changes; do not apply late results from old inputs. Necessary clarification may use at most two questions; the implemented tracer can proceed without questions when the goal and materials suffice.

## Phase 5 — Expand engine configuration after the tracer

1. Reflections: preserve the delivered slice and its regression coverage.
2. Socratic: validate the original conceptual-understanding tracer.
3. SDL: propose focus, starting point and ending point. Keep diagnostic, lesson and practice generation in the existing instructor Review activity flow; the copilot cannot supply an unreviewed learning plan.
4. Debate: propose scenario, competing positions and evidence requirements within the existing scenario/instructions fields, opening prompt and minimum messages. Do not add fictitious engine fields.
5. AIducate: enable only after its runtime contract, schema and review flow exist.

Configuration proposal support is not evidence of student-engine quality or hosted operation. Runtime bugs and engine-specific pedagogy evaluation remain separate work with their own verification.

## Verification and remaining gates

Use an isolated PostgreSQL/pgvector database, not a shared course database. Mock model calls in automated tests; independently run the installed local model against controlled samples. Run the copilot, existing Reflections, assignment and frontend regressions plus production build and whitespace checks.

See [current verification and manual tests](docs/assignment-copilot-verification.md) for exact evidence, commands and outstanding browser/real-retrieval checks. No deployment, production migration or publication is part of this implementation.
