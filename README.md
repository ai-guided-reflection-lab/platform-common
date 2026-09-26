# ClubALL learning platform

One professor entry screen for **Socratic Chat**, **Reflections**, and **Student Agent Bot**, and one student assignment list that launches the assigned tool with its saved configuration.

## Run with Docker

```bash
cp .env.example .env
# Edit .env: set independent AUTH_SESSION_SECRET and PLATFORM_SERVICE_TOKEN values,
# and the model-provider keys needed by the tools you use.
docker compose up --build
```

Open **http://localhost:8000**. Login and account setup use the existing Socratic authentication flow, then redirect to `/platform/`.

The root Compose file starts the public platform, two private learning services, and PostgreSQL with separate `cluball` and `cluball_reflections` databases. Only the platform exposes a host port. PostgreSQL, uploaded documents, the RAG index, tutor sessions, and downloaded embedding models use persistent volumes. Keep those volumes when restarting.

`POSTGRES_PASSWORD` in `.env` configures the local Compose database. Its two application database URLs are set by Compose; `.env` database URLs are used for non-Docker development. Use a URL-safe password or encode special characters in connection URLs.

The first Reflections milestone request may download its existing `stsb-roberta-large` embedding model. Topic-based reflection and tutor conversations require a configured model provider. Socratic retains its existing extractive answer fallback when no OpenAI key is configured. Tutor topic generation additionally requires Firecrawl.

## Socratic questioning pipeline

Socratic assignments use the same end-to-end teaching pipeline as the standalone Socratic Chat application:

1. Classify the learner's intent, target concept, dialogue state, and requested action.
2. Retrieve relevant passages with dense embeddings and PostgreSQL full-text search.
3. Evaluate substantive learner answers against the retrieved course evidence.
4. Track per-concept evidence and move learners through emerging, developing, verification-ready, and mastered states.
5. Select a Socratic strategy and disclosure level based on the learner's current understanding and prior turns.
6. Generate and validate one grounded response, or produce a safe pause/close transition.
7. Record privacy-safe stage logs for diagnosis without logging raw learner messages by default.

Publishing an assignment stores an immutable copy of the selected document chunks and their embeddings. Later document edits or deletions therefore do not change an already-published assignment. PostgreSQL uses the `pgvector` image because document ingestion and hybrid retrieval require the vector extension.

## Accounts and courses

- For an institutional deployment, use `AUTH_MODE=school_google`, configure `GOOGLE_CLIENT_ID`, allowed domains and the application origin, and set `ADMIN_EMAILS`. Existing Google verification, instructor approvals, and optional GitHub linking are preserved.
- With `AUTH_MODE=open`, register local accounts at `/`. When
  `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and `GITHUB_CALLBACK_URL` are
  configured, the same login form also offers GitHub authentication using a
  verified GitHub email; it requests no repository access. Registration
  produces student accounts. To bootstrap a professor/admin, use the explicit
  database administration command below after registering:

```bash
docker compose exec platform python scripts/set_role.py professor@example.edu instructor
```

For a local Python installation, use `.venv/bin/python scripts/set_role.py professor@example.edu instructor` instead.

Instructors use **Courses & access** to create courses, approve students, and
manage course materials. Students use the unified **Dashboard** to request
course access and expand an approved course card to open its assignments.

## Professor workflow

1. Select one of the three tools from the professor dashboard.
2. Select a course and choose **New assignment**.
3. Enter a title, student instructions, optional due date, and recipients.
4. Configure the selected tool:
   - **Socratic Chat:** upload/select TXT, Markdown, HTML, LaTeX, Word (`.doc`/`.docx`), or PDF course documents, set an opening prompt, and choose a minimum message count.
   - **Reflections:** configure topics/sub-topics, depth, probing style, application requirements, and notes; or choose a milestone prompt with historical CSV data.
   - **Student Agent Bot:** select a built-in topic, import topic JSON, create a custom topic, or generate a draft. Edit reading resources, practice stages/scenarios, questions, worked example, and provider.
5. Save a draft or publish it. Published work appears in the recipients' student dashboards.

### Import from UNC Charlotte Canvas

The Socratic Chat professor dashboard can create a draft from an assignment visible
to your UNC Charlotte Canvas account:

1. In Canvas at [instructure.charlotte.edu](https://instructure.charlotte.edu),
   open **Account → Settings → Approved Integrations** and create a current access
   token. If **Add New Access Token** is unavailable, request API access through
   UNC Charlotte Canvas support; the university controls whether personal tokens
   are enabled.
2. Open **Socratic Chat** in the professor dashboard and select the destination
   ClubALL course. If it does not exist yet, select the Canvas class and create
   its corresponding ClubALL course from the import panel.
3. Under **Import from UNC Charlotte Canvas**, choose the chatbot students will
   use, paste the token, select an active Canvas course, and select one of the
   assignments visible to that account.
4. Import the assignment as a draft, review the copied title, instructions, due
   date, and assigned chatbot, configure the selected learning experience, choose
   recipients, and publish.

The connector is read-only and is restricted to
`https://instructure.charlotte.edu/api/v1`. The access token is held in browser
memory only for the current page and sent to the ClubALL backend only for the
requested Canvas operation. It is not written to PostgreSQL, browser storage,
application logs, assignment configuration, or source files. Importing copies a
point-in-time assignment draft; later Canvas edits are not synchronized.

### Add ClubALL as a Canvas External App (LTI 1.3)

The personal-token importer above and the LTI integration serve different
purposes. The importer copies existing Canvas assignments into ClubALL. LTI lets
Canvas users open ClubALL from course navigation with a signed Canvas identity
and course context, without entering another password or pasting an API token.

The first LTI milestone supports **Course Navigation**:

- Canvas validates the configured ClubALL public key.
- ClubALL validates the Canvas launch signature, issuer, client ID, deployment
  ID, nonce, and one-time state.
- The first instructor launch creates a private linked ClubALL course.
- Later instructor and student launches create or link accounts by the signed
  Canvas identity and approve the matching course membership.
- Students are added to published whole-course assignments when they first
  launch from Canvas.

ClubALL must be available at a stable public HTTPS origin. `localhost` cannot be
used for an institutional Canvas installation.

1. Generate a dedicated RSA key outside the repository:

   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out cluball-lti-private.pem
   base64 < cluball-lti-private.pem | tr -d '\n'
   ```

2. Store the Base64 output only in the deployment environment and initially
   configure:

   ```dotenv
   LTI_PUBLIC_BASE_URL=https://cluball.example.edu
   LTI_TOOL_PRIVATE_KEY_B64=<base64-private-key>
   LTI_TOOL_KEY_ID=cluball-lti-1
   ```

3. Ask a UNC Charlotte Canvas administrator to create an **LTI Developer Key**.
   Canvas can import the JSON served at
   `https://cluball.example.edu/api/lti/canvas-config`, or the administrator can
   enter its OIDC initiation, launch, and public JWKS URLs manually. Enable the
   Developer Key and copy its Client ID.
4. In the target Canvas account or course, open **Settings → Apps → View App
   Configurations → + App**, choose **By Client ID**, enter the Client ID, and
   install ClubALL. Copy the resulting Deployment ID.
5. Complete the deployment environment and restart ClubALL:

   ```dotenv
   LTI_CANVAS_ISSUER=https://instructure.charlotte.edu
   LTI_CLIENT_ID=<canvas-developer-key-client-id>
   LTI_DEPLOYMENT_ID=<installed-app-deployment-id>
   LTI_PLATFORM_JWKS_URL=https://sso.canvaslms.com/api/lti/security/jwks
   ```

6. Verify `/api/lti/status` reports both
   `tool_configuration_ready: true` and `launch_configured: true`. An instructor
   must launch ClubALL once from the Canvas course before students launch it.

Never commit the RSA private key, Client ID/deployment configuration for a
private institution deployment, or other Canvas administrator credentials.
Assignment deep linking, roster synchronization (NRPS), and grade return (AGS)
are intentionally deferred until the course-navigation launch is approved and
tested by the institution.

Published settings are immutable. Socratic snapshots the selected indexed document content; Reflections creates a private assignment module; Tutor stores a complete topic snapshot. Editing or deleting source materials does not alter published work. **Duplicate as draft** creates a new editable assignment; **Archive** removes student access while retaining results for the professor.

The progress view lists each recipient's status and available results. Whole-course recipients are the approved students enrolled **at publication time**. Later enrollments are not added automatically. Revoking enrollment immediately removes assignment access. Due dates are informational; late work remains allowed.

## Student workflow

The student Dashboard combines course access and assignments across all three
tools. Select **Assignments** on an approved course card to enlarge it and show
that course's work, then open an assignment to start or resume its session.
Students do not choose their identity, module, topic, model, or tool
configuration.

- Socratic: complete after the configured minimum number of student messages.
  While the assistant is generating, the conversation shows elapsed time. The
  latest tutor card includes the previous-answer score, a highlighted next
  thinking step, an expandable question rationale, suggested responses, and
  clickable evidence passages from the assignment's frozen course documents;
  active concepts are emphasized in bold. Press Enter to send a response or
  Shift+Enter to add a new line.
- Topic-based Reflections: finish the session to save an evaluation.
- Milestone Reflections: submitting the reflection completes the assignment and shows related experiences.
- Tutor: progress through the learning phases and complete at wrap-up, or let the tutor close the completed lesson.

There is one persistent attempt per student per assignment. Reopening resumes that attempt; completed work opens read-only with its transcript/results. To assign a second attempt, publish a duplicate assignment.

For Reflections, **Start assignment** (or **Resume assignment** / **View reflection results**) opens the original Reflections student interface in a new tab. The tab uses the signed-in platform account and published assignment settings automatically, including the topic chat, timer, evaluation, or milestone reflection and similar experiences. Returning to the assignment tab refreshes its progress. Build the platform frontend to bundle both interfaces; no separate Reflections frontend server is needed. The private Reflections backend and its configured model provider must still be running.

## Local development

Python 3.12, Node 22+, and PostgreSQL are suitable for this workspace. The projects run in separate Python processes because both Socratic and Reflections use the package name `app`.

The repository-root `.python-version` pins Python 3.12 for native deployments
such as Render. Keep the Render service root at the repository root when
deploying the unified platform; its build command is
`pip install -r requirements.txt && cd platform_frontend && npm ci && npm run build`,
and its start command is
`python -m uvicorn platform_app.main:app --host 0.0.0.0 --port ${PORT:-10000}`.
The root `render.yaml` records these settings for Blueprint deployments. For an
existing manually configured Render service, copy these commands into
**Settings → Build & Deploy**; do not use Render's placeholder
`gunicorn your_application.wsgi` command because ClubALL is a FastAPI ASGI
application. Enter the command without surrounding quotation marks. The
`platform_app` module is available only when Render's **Root Directory** is
blank (the repository root), not `Socratic-Chat/backend`.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt

python3.12 -m venv reflections-app/.venv
reflections-app/.venv/bin/python -m pip install -r reflections-app/backend/requirements.txt
python3.12 -m venv student-agent-bot/.venv
student-agent-bot/.venv/bin/python -m pip install -r student-agent-bot/requirements.txt

cd platform_frontend
npm ci
npm run build
cd ..

cp .env.example .env
# Create the two databases and configure their URLs/secrets/provider keys in .env.
REFLECTIONS_PYTHON="$PWD/reflections-app/.venv/bin/python" \
TUTOR_PYTHON="$PWD/student-agent-bot/.venv/bin/python" \
  .venv/bin/python scripts/run_local.py
```

Open http://127.0.0.1:8000. The runner starts the gateway on 8000, Reflections on 8002, and Tutor on 8003, all bound to loopback. Stopping it stops all three. Install dependencies first and use absolute paths for the optional interpreter overrides.

### Docker Compose

The Compose deployment starts the platform gateway, Reflections, and Tutor while using the host PostgreSQL/pgvector database configured for DBeaver:

```bash
docker compose -f compose.yaml up --build
```

The gateway is available at http://127.0.0.1:8000. The containerized services use `DOCKER_DATABASE_URL` from `.env` to reach the host database on port 5434 and `host.docker.internal` to reach Ollama running on the host at port 11434. This means native and Docker runs share accounts, courses, documents, and evaluations. Stop the stack with:

```bash
docker compose -f compose.yaml down
```

To remove the Docker database and other persisted service data as well, use `docker compose -f compose.yaml down -v`.

The isolated PostgreSQL service remains available only for explicit experiments with `docker compose --profile isolated-db ...`; it is not used by the main Docker deployment.

For frontend iteration with shared authentication, run `npm run build -- --watch` in `platform_frontend` and refresh the gateway page after changes. This keeps login and the UI on one origin. The optional Vite development server proxies API requests, but using it on another port requires a same-origin login proxy because browser sessions are stored per origin.

## Structure and integration boundaries

```text
platform_app/             Shared assignment API, authorization, engine adapters
  migrations/            Versioned platform schema migrations
platform_frontend/       Shared React UI and separate tool configuration screens
Socratic-Chat/            Existing identity, courses, documents, RAG engine
reflections-app/          Existing reflection graphs, analytics and recommendations
student-agent-bot/        Existing phased tutor, plus durable JSON session storage
scripts/                 Local runner, role bootstrap, database initialization
platform_tests/          Assignment integration tests
compose.yaml             One public origin and private learning services
```

The shared backend reuses Socratic's authentication and course APIs. PostgreSQL is divided into explicit namespaces:

- `platform`: shared identity, course, enrollment, assignment, recipient, and attempt tables. Every table ends in `_platform`.
- `socratic_chat`: Socratic conversations, messages, progress, assessments, files, and document chunks. Every table ends in `_socratic_chat`; user and course foreign keys point into `platform`.
- `reflections_app`: reflection modules, configurations, conversations, analytics, and LangGraph checkpoints. Every table ends in `_reflections_app`; new platform sessions reference `platform.users_platform` and `platform.courses_platform` directly. The legacy student table remains only to preserve historical standalone Reflections sessions.

Tutor uses a persistent SQLite file configured with `TUTOR_SESSION_DB`. Platform, Socratic Chat, and Reflections use the single PostgreSQL connection in `DATABASE_URL`; their schemas isolate service-owned data. Configure `PLATFORM_DB_SCHEMA`, `SOCRATIC_DB_SCHEMA`, and `REFLECTIONS_DB_SCHEMA` when using non-default schema names. The bundled PostgreSQL container is available only through the optional `isolated-db` Compose profile; the default Docker stack uses the host database configured by `DOCKER_DATABASE_URL`.

The browser calls `/api/platform/...`; the gateway chooses the appropriate engine and derives student/session identity from the signed account session. Internal service calls require `X-Platform-Service`, using the common `PLATFORM_SERVICE_TOKEN`. Internal endpoints are unavailable without a token, even in standalone mode. Public platform APIs reject the old `X-User-Id` shortcut.

Platform migrations run once on gateway startup under a database migration lock. Existing Socratic accounts/courses can be reused by setting `DATABASE_URL` to their database. Existing reflection modules and tutor topic files remain available in their original applications; they are not automatically converted into assignments or matched to student identities. Import a topic or configure a new assignment for the shared platform. This avoids guessing recipients or publishing historical content.

## Verification

The PostgreSQL tests create and drop uniquely named schemas. Set `TEST_DATABASE_URL` to an available development/test database whose user can create schemas. They do not alter existing application tables and do not call paid model APIs.

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres \
  .venv/bin/python -m pytest platform_tests -q

# Run each engine suite separately to avoid their conflicting `app` module names.
# Install pytest and httpx in the corresponding virtual environments first.
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres \
  reflections-app/.venv/bin/python -m pytest reflections-app/backend/tests -q
student-agent-bot/.venv/bin/python -m pytest student-agent-bot/tests -q
PYTHONPATH=Socratic-Chat/backend .venv/bin/python -m pytest Socratic-Chat/backend/tests -q

cd platform_frontend
npm test
npm run build
```

Tests cover assignment ownership and visibility, publication rollback, frozen content, recipient/enrollment rules, start races, message retry deduplication, completion, service authentication, engine restart recovery, tool selection, student routing, and frontend failure/retry behavior. Model calls are simulated in engine tests; live provider quality and deployment-specific Google sign-in require configured credentials.

### Reflections provider configuration

If Reflections reports a missing or invalid AI provider key, update `GROQ_API_KEY` or `OPENAI_API_KEY` (matching `LLM_PROVIDER` and any role overrides) in the **root `.env`**. Root Docker Compose does not load `reflections-app/backend/.env`; configure the corresponding `GROQ_MODEL` or `OPENAI_MODEL` in the root file too. Apply environment changes with `docker compose up -d --force-recreate reflections` rather than `docker compose restart`, then retry the assignment. Existing checkpointed sessions are retained.
