# CourseLab interface rework

This is the existing main interface, reworked around assignment creation and student learning. It does not contain the superseded standalone course dashboard or demo-role login system from PR #9.

## Run

For an existing Render deployment, follow [Add SDL and shared documents](render-sdl.md). The standalone `render.sdl.yaml` adds just the missing backend; the full `render.yaml` defines all three services.

Copy `.env.example` to a private `.env`. Configure independent `AUTH_SESSION_SECRET` and `PLATFORM_SERVICE_TOKEN` values, `DATABASE_URL`, and `DOCKER_DATABASE_URL` (the database URL reachable from containers). Set the AI provider keys used by your chats and embeddings. No credentials or test accounts are included in this change.

```sh
docker compose up --build
```

Open `http://localhost:8000`. The platform connects to private SDL and Reflections services. The SDL service uses `ADAPTIVE_PLATFORM_ONLY=true`; its API requires the platform service token. Do not expose that service's port publicly. The legacy tutor is optional via `--profile legacy-tutor`.

For native development, install root `requirements.txt` in the platform environment and `adaptive-learning-app/backend/requirements.txt` in a separate SDL environment. Build `platform_frontend` with `npm ci && npm run build`. Start the gateway with `python -m uvicorn platform_app.main:app --host 127.0.0.1 --port 8000` from the repository root. Start SDL with `python -m uvicorn app.main:app --host 127.0.0.1 --port 8100` from `adaptive-learning-app/backend`, supplying the same database and service token and setting `ADAPTIVE_PLATFORM_ONLY=true`. Reflections retains its separate environment and service setup.

## Course and identity context

The existing authentication and Canvas launch exchange remain in use. Canvas supplies `?course=<platform-course-UUID>`; the browser remembers that course within the signed-in session. Every data operation checks approved course membership. Local testing can explicitly set `PLATFORM_LOCAL_COURSE_CODE` to an existing course code. It does not create a course or grant membership. User accounts, course creation and instructor-role administration retain the existing backend APIs and administrative setup; the new interface has no course-selection page.

## Current flows

- Instructors start at All assignments. Create activity collects details, indexed or newly uploaded materials, activity choice, then chat-specific settings. Drafts persist their settings. Review exposes the generated SDL lesson, including its diagnostic answer keys and practice rubrics. Publish freezes the activity and recipient snapshot.
- Published activity pages show quick completion statistics and assignment details. Average grade is shown only if an engine provides an explicit percentage. Detailed Insights opens the Analytics placeholder.
- Students see New, In progress, Completed and All assignments vertically. List/grid icon controls remember the view locally. The instructor determines which chat opens.
- SDL uses the existing `LessonWorkspace` and learning-turn API inside the platform shell. Old `self-directed.html?assignment=...` links redirect to the normal assignment route. Quiz, hints, adaptive practice, reflection and saved state are owned by SDL, not reimplemented in the shared platform.
- Short-lived, account-scoped browser snapshots avoid waiting for network reads on every navigation. Fresh reads revalidate in the background; platform writes invalidate snapshots. Cross-service student identity mappings are cached for five minutes, but authorization remains checked on every request.

## Chat integration boundaries

| Chat | Connection |
| --- | --- |
| Socratic | Existing pipeline; publishing snapshots selected shared document chunks. |
| Reflections | Existing external service adapter and original student UI. Shared document IDs are platform metadata; the Reflections owner must integrate retrieval if desired. |
| SDL | Preparation, publication, recipient identity, saved lesson state and progress use the SDL service. |
| Debate | Native scenario-based provider adapter and common student conversation. Uploaded documents are not automatically inserted into Debate replies. |
| AIducate | Draft storage only; publishing reports that its backend is missing. |

No chat-specific Socratic or Reflections engine source is redesigned. Student Agent is absent from the new choices and lists; this change does not erase historical assignments or their stored data.

## Shared documents and database migration

Uploads use the SDL-derived parsing, chunking and embedding pipeline. The common database layer stores files in `SHARED_RAG_DB_SCHEMA.documents` and indexed text/vectors in `SHARED_RAG_DB_SCHEMA.chunks` (default schema `shared_rag`). SDL publication copies selected source evidence into its immutable lesson store. Socratic publication snapshots the same shared chunks.

On initialization, the database layer transactionally moves and renames the legacy Socratic RAG tables into the shared namespace without copying or deleting their records. If legacy and destination tables both exist, startup stops for manual reconciliation. Back up the target database and coordinate other services still reading the old names before rollout. Migration `007_activity_choices.sql` adds the new activity types while retaining historical values. No migration deletes student data.

Authenticated developer API:

- `GET /api/platform/courses/{course_id}/documents`
- `POST /api/platform/courses/{course_id}/documents/upload` (instructor; multipart `files`)
- `POST /api/platform/rag/chunks` with `course_id`, `document_ids`, optional `offset` and `limit`
- `POST /api/platform/rag/search` with `course_id`, `document_ids`, `query` and optional `limit`

Use the existing signed platform bearer session. Course membership and document ownership are enforced. Chunk responses omit embeddings and include `total` and `next_offset`; retrieval returns ranked evidence. Never publish the internal service token to a browser client.

## Reflections Assignment Copilot

The Reflections settings include a local Assignment Copilot above the existing
manual controls. It supports topic and milestone reflection; other activity
types are unchanged. Setup and native/Docker URLs are in the
[README](../README.md#reflections-assignment-copilot).

`POST /api/platform/copilot/reflections/propose` requires the signed professor
session and approved management of `course_id`. It accepts `goal` (10–2,000
characters), 1–100 selected indexed `document_ids`, and optional `current`
fields (`title`, `instructions`, `module_type`). Unknown fields, including
`historical_data`, are rejected. Document IDs are normalized and deduplicated;
missing or cross-course IDs are rejected before inference.

The only agent tools list selected documents and search selected course
materials. The server fixes the course/selection, validates arguments, bounds
results, and maps source IDs to actual retrieved excerpts and filenames.
Document passages are explicitly untrusted data. There are at most four model
requests (including one optional JSON repair) and six tool calls, even if larger
limits are configured. Lower limits can be configured. Repair cannot run tools.
No prompts, reasoning, document passages or historical responses are logged by
the copilot. Conversations and proposals are not persisted; no migration is
needed. An unavailable model returns 503; an invalid or ungrounded proposal
returns 502 with manual configuration still available.

Applying a proposal changes only local form state, retains uploaded milestone
CSV and selected documents, and returns the activity to editable configuration.
Changing the goal, selected materials or reflection mode makes the proposal
stale; regenerate or dismiss it. Only the existing Save draft and Publish
activity actions persist or publish. Model/provider settings and all student
Reflections behavior remain owned by their existing services.

Automated checks (model calls mocked; integration checks require a dedicated
PostgreSQL database with pgvector and schema-creation privileges):

```sh
.venv/bin/python -m pytest -q platform_unit_tests/test_reflection_copilot.py platform_tests/test_reflection_copilot.py platform_tests/test_assignments.py
cd platform_frontend
npm test -- src/reflection-copilot.test.jsx src/create-activity.test.jsx
npm run build
```

Manual test prerequisites: run the platform, PostgreSQL, SDL/shared search and
Reflections services; start Ollama with the configured model installed; sign in
as a professor managing a course with an indexed document.

1. Open Create New Activity, select an indexed document, then choose Reflections.
2. Enter a specific reflection goal and select Prepare proposal.
3. Confirm the preview shows rationale and excerpts from the selected document,
   while the existing title, description and settings have not changed.
4. Select Apply proposal. Confirm the form is populated and every field remains
   editable. Edit a sub-topic, save a draft, reopen it, and confirm persistence.
5. Change the goal or document selection after generation. Confirm the old
   proposal cannot be applied and can be regenerated or dismissed.
6. Stop Ollama and prepare a new proposal. Confirm an actionable error appears
   and manual Reflections configuration and draft saving still work.
7. Restart Ollama. Choose Milestone reflection, upload a CSV, prepare and apply
   a proposal. Confirm the CSV remains attached and the copilot network request
   contains no `historical_data` or CSV content. Save/reopen to confirm retention.

Expected: grounded proposals preview before application; application only edits
the form; persistence and publication require explicit instructor actions.
Automated mocks do not establish live model quality or institutional Canvas
behavior. Record live success and provider-unavailable results separately.

See the [implementation verification record](reflection-copilot-verification.md)
for local results and remaining live checks.

## Verification and remaining work

The frontend build and 48 frontend checks passed after the final deployment packaging pass. Five mocked platform service-boundary checks and 60 focused SDL flow/bridge/retrieval checks passed. These checks do not establish the quality of generated teaching content.

Local manual checks confirmed saved draft restoration, assignment navigation, student list/grid views, embedded SDL lesson resumption, and a live Debate reply (user verified). The configured provider subsequently passed generation and embedding probes. A user-created SDL lesson was generated/published and opened with saved state; this is not a complete automated end-to-end journey.

Reflections end-to-end service verification, real institutional Canvas launches and newly joining Canvas students receiving an already-published SDL lesson still need deployment testing. Detailed Analytics is a placeholder. SDL's final completion policy remains deferred to its workflow owner. AIducate has no engine. No production deployment, database reset or automatic merge is part of this change.
