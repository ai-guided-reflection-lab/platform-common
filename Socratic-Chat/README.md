# Socratic-Chat

A clean personal workspace for a retrieval-augmented chatbot.

The backend indexes course documents with OpenAI embeddings, retrieves relevant
PostgreSQL chunks, and uses either OpenAI or Groq for student-state
classification, conditional learning evaluation, and grounded Socratic
responses. OpenAI embedding credentials remain required for document indexing
and semantic retrieval.

## Setup

```bash
cd Socratic-Chat
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp .env.example .env
```

Add `OPENAI_API_KEY` for document embeddings. The conversational LLM roles use
Groq by default:

```env
OPENAI_API_KEY=your-openai-key
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-key
GROQ_API_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-120b
GROQ_CLASSIFIER_MODEL=openai/gpt-oss-120b
GROQ_ANSWER_EVALUATION_MODEL=openai/gpt-oss-120b
```

Document ingestion and query retrieval continue to use
`text-embedding-3-small` with 1,536 dimensions. Restart the service after
changing these variables.

The classifier, answer evaluator, and tutor generator all use Groq's
`openai/gpt-oss-120b` model
while document embeddings remain on OpenAI. To switch conversational roles back
to OpenAI, set:

```env
LLM_PROVIDER=openai
OPENAI_API_BASE_URL=https://api.openai.com/v1
RAG_MODEL=gpt-4.1-mini
```

Hybrid retrieval applies a relevance gate before any answer or Socratic example
is generated. A chunk is retained when PostgreSQL full-text search finds lexical
evidence or its absolute cosine similarity reaches `RAG_MIN_DENSE_SIMILARITY`
(default `0.42`). Rank-fusion scores decide the order of retained chunks; they
are not treated as proof of relevance. If every candidate is rejected, the
pipeline returns the grounded “not found in uploaded notes” response without
calling the generation model. Tune the threshold against a labeled set of
course questions rather than lowering it simply to force results.

## Socratic questioning pipeline

Each learning message passes through a hybrid interpretation stage before RAG
retrieval. Session commands, access checks, and safe fallbacks remain
deterministic. The configured classifier (Groq `openai/gpt-oss-120b` by default) returns validated labels
for the student's intent, question type, target concepts, current demonstrated
understanding, required support level, dialogue status, next conversation action,
and focused retrieval queries. The status distinguishes
ordinary learning, a substantive claim asking for confirmation, a bare claim of
understanding, acknowledgement, topic change, and a request to close. Invalid
JSON, unsupported labels, or a provider failure automatically falls back to the
rules.

Operational chat requests—such as listing published documents or asking for the
course title—are selected from the classifier's structured `operational_request`
field. They are no longer detected by loose keyword combinations such as
`files + have`. Ordinary mentions of files, folders, documents, or unrelated
topic words proceed through classification and RAG. Unsupported topics are
rejected by configurable sparse and dense retrieval thresholds rather than a
fixed list of words, and the generator is instructed to use only retrieved
instructor-published evidence. Unsupported requests receive a short boundary
message instead of an answer from the model's general knowledge.
Classification uses strict JSON Schema output to keep these semantic routes
reliable.

After retrieval, the teaching policy chooses one explainable action. A new
concept begins with a short document-grounded example and one discovery
question; comparisons use contrasting cases; procedure, application, and
debugging requests use an incomplete scenario. Uncertainty or an explicit hint
request increases disclosure. Repeated difficulty raises the classifier's
support level and produces a clear explanation plus a simpler, meaningfully
different example; continued difficulty permits a step-by-step example. Teaching
instructions guide disclosure, examples, and a focused question; there is no
deterministic response rewriter guaranteeing compliance. A substantive claim is prompted to receive a short grounded
`Yes—`/`Partly—`/`Not quite—` check before one revision question. A bare “I
understand” receives a transfer or teach-back check instead of unearned praise.
Acknowledgements and clear endings are routed to a short, question-free response
instead of another Socratic prompt.

Question categories remain internal planning labels. Student-facing questions
use plain language and name a concrete action, choice, example, or outcome from
the current topic rather than canned stems such as `What evidence?` or `What
factor?`. A substantial pasted passage receives one neutral reflection before
the question. Prompt instructions discourage malformed Markdown and incomplete
choice prompts such as `Which scenario?` when no choices are presented.

Conversations recover their original learning topic from stored history. A
different topic is redirected to a new chat; short follow-ups and requests to
define a term in the current scenario remain attached to that scenario. Retrieval
combines the main query, original topic, and up to two classifier subqueries,
deduplicating chunks while preserving coverage across queries.

The frontend uses `POST /api/chat/stream` for real pipeline-stage updates followed
by the final response (not token-by-token generation). The existing `/api/chat`
endpoint remains available. Message timestamps and eligible answer scores are
shown in the conversation. “Draft an example answer” retrieves course evidence
and fills the composer without saving or submitting the draft.

Substantive responses to tutor questions pass through a separate hybrid answer
evaluator. It calculates deterministic course-concept coverage (20%), model-based
semantic alignment (20%), and a grounded rubric for correctness, completeness,
reasoning, and application (60%). Application is stored as `NULL` and excluded
from the rubric denominator when the tutor did not ask for transfer or application;
zero now means application was requested but not demonstrated. The evaluator also
compares recent responses and records whether understanding improved. Retrieval rank is never used as a learning
score. The evaluator uses the preceding tutor question as part of retrieval so
short replies remain attached to the correct topic. Questions, acknowledgements,
requests for help, and unsupported topics are not scored.

Each eligible assessment is appended to `mastery_assessments`, while an
exponentially weighted estimate and evidence count are stored in
`student_concept_progress`. A single strong answer cannot complete a concept.
After at least two supporting answers and an estimate of 80 or above, the tutor
asks one transfer or teach-back verification question. A second high-quality
application answer completes the current objective. Critical misconceptions cap
the assessment below the verification threshold. Displayed scores
should be treated as adaptive tutoring signals, not official
grades. Correct and nearly correct responses receive concise, specific feedback
before the next learning step.

The configured evaluator uses structured JSON output. Empty or incomplete
evaluator responses are rejected and logged instead of being converted into
zero-score database records. The persisted conversation concept is reused for
follow-up answers so a short reply cannot be stored under a generic `current
concept` key.

Set `CLASSIFIER_ENABLED=false` to use deterministic classification only. By
default the classifier uses `RAG_MODEL`; set `CLASSIFIER_MODEL` only when a
separate OpenAI classification model is desired. For Groq, use
`GROQ_CLASSIFIER_MODEL` and `GROQ_ANSWER_EVALUATION_MODEL` overrides.
Set `ANSWER_EVALUATION_ENABLED=false` to disable adaptive assessment. By default,
the evaluator uses `RAG_MODEL`; `ANSWER_EVALUATION_MODEL` can override it.

These are three logical LLM roles: student-state classification, conditional
learning-progress evaluation, and grounded response generation. The evaluator is
skipped for a new topic, acknowledgement, unsupported request, or other message
that does not demonstrate an answer to a tutor question.

## Add Documents

Put `.txt`, `.md`, `.pdf`, `.tex`, `.html`, or `.htm` files in:

```text
backend/data/raw_docs/
```

Then start the backend and press **Scan documents** in the UI.

### Chunking behavior

Instructor uploads are split by document structure before retrieval. HTML and
Markdown headings become section boundaries, paragraphs remain intact, and each
chunk receives a document-and-section breadcrumb plus retrieval metadata.

- The Software Engineering 3155 core uses a 300-token target, a 500-token limit,
  and up to 40 tokens of same-section overlap.
- *Software Engineering at Google* chapters use a 650-token target, a 900-token
  limit, and up to 100 tokens of same-section overlap.
- Other documents use a 450-token target, a 700-token limit, and up to 80 tokens
  of same-section overlap.

Chunks never overlap across heading boundaries. Re-uploading a previously indexed
document replaces its older chunk layout rather than retaining stale duplicates.
Assignment requests are hard-filtered by structural assignment metadata before
retrieval, so a cross-reference to Assignment 1 inside Assignment 2 cannot leak
Assignment 2 content into an Assignment 1 answer.

### Software Engineering 3155 corpus

The Fall 2026 Socratic tutoring corpus is generated from the course overview and
Assignments 1–5. Human-readable and retrieval-ready artifacts are stored in:

```text
docs/rag/software-engineering-3155-fall-2026/
```

The current lexical RAG scanner reads the semantic Markdown units named
`backend/data/raw_docs/se3155-*.md`. Regenerate every representation after
editing the source structure:

```bash
python tools/build_se3155_corpus.py
```

The JSONL version preserves assignment, content-type, confidence, privacy, and
verification metadata for a future vector-embedding pipeline. The corpus follows
the course AI policy: no chatbot assistance on quizzes, no assignment code from
scratch, and code-level help only for debugging a learner's own attempt.

## Run

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000
```

## API

- `GET /health`
- `POST /api/documents/text`
- `POST /api/documents/scan`
- `POST /api/chat`


## PostgreSQL conversation memory

The chatbot saves every user and assistant message in PostgreSQL. It also stores
the conversation's latest LLM-derived dialogue status, active concept, and
whether the session is active, paused, or completed. These fields describe the
current interaction; they are not a student mastery score.

1. Create a database:

```bash
createdb my_rag_chatbot
```

2. Add this to `.env`:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/my_rag_chatbot
```

Change the username, password, host, and database name to match your PostgreSQL setup.

3. Install the database driver:

```bash
cd backend
../.venv/bin/python -m pip install -r requirements.txt
```

4. Restart the server:

```bash
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app creates these tables automatically on startup:

- `conversations`
- `conversation_messages`
- `mastery_assessments` (one immutable record per evaluated student answer)
- `student_concept_progress` (the latest per-student, per-course concept state)

## Chat pipeline logs on Render

Each chat request, including `POST /api/chat/stream`, writes concise structured events to stdout with a
unique `trace_id` and elapsed milliseconds. Render is configured with `PYTHONUNBUFFERED=1`, so these
events appear immediately in the service's Application Logs. Search for the
exact field `trace_id=<id>` to follow one request across routing, retrieval,
generation, saving, and response return.

Message and conversation-history content is not logged by default. Setting
`DEBUG_PIPELINE_LOGS=true` adds redacted, truncated previews of retrieved chunks,
fixed prompt instructions and generated answers,
along with character counts and non-reversible SHA-256 fingerprints. It never
logs complete prompts or documents and remains disabled by default. Enable it
only temporarily while diagnosing answer generation, then turn it off again.

File logging is opt-in: `PIPELINE_LOG_FILE` sets a rotating log file.
`LOG_FULL_PROMPTS=true` together with `PIPELINE_PROMPT_DIR` enables full
request/result snapshots. These snapshots can contain private student messages
and course content; leave them disabled on Render unless explicitly needed for
authorized debugging. Do not commit snapshots. Hosted operation does not require
these files, a local model, or a database/vector-dimension migration.

Check the connection:

```text
http://127.0.0.1:8000/api/db/status
```

## UNC Charlotte account access

The deployed app uses GitHub as its school identity provider. It requests the
read-only `user:email` OAuth scope, reads the authenticated user's email list,
and accepts only an address that GitHub marks as verified with the exact domain
`charlotte.edu`. Repository access is never requested. Google and Duo are not
part of this sign-in path.

Configure these environment variables on the Render backend:

```text
AUTH_MODE=school_github
ALLOWED_GITHUB_EMAIL_DOMAINS=charlotte.edu
AUTH_SESSION_SECRET=A_LONG_RANDOM_SECRET
AUTH_SESSION_MINUTES=60
ALLOW_PASSWORD_LOGIN=true
CORS_ALLOWED_ORIGINS=https://jamesonthehill.github.io,https://jamesonthehill.com
```

Generate `AUTH_SESSION_SECRET` with `openssl rand -hex 32`. Keep it only in
Render's environment settings or a local `.env`; never commit its value.

The GitHub Pages frontend reads the Render API address from
`frontend/config.js`. The backend exchanges the GitHub callback for a short-lived,
single-use app login code and then issues a signed session.

## Roles and one-time account setup

After the first successful school GitHub sign-in, a user completes one account
setup form with a Socratic-Chat username and requested position. The setup form
is shown only once. New users must begin with GitHub verification; returning
users can use either GitHub or the Socratic-Chat ID and password they created.

The `users.authority_level` column controls backend authorization:

- `0` — administrator
- `1` — instructor
- `2` — student

Students become active immediately. Choosing instructor creates a pending
request while the account remains at student authority. An administrator can
approve or reject the request from the course dashboard. Users cannot grant
themselves instructor or administrator access.

Open registration remains disabled in `school_github` mode, so a visitor cannot
create an account without a verified school address on GitHub. Password login
is available only to accounts that have already completed that verification and
one-time setup.

Set at least one administrator in the Render environment before deployment:

```text
ADMIN_EMAILS=admin-account@charlotte.edu
```

Multiple administrator emails may be separated with commas. The backend adds
the role and onboarding columns automatically during startup. Instructor-only
document APIs are also protected by the backend, not only hidden in the UI.

### Configure GitHub school authentication

Create a GitHub OAuth App under **GitHub Settings → Developer settings → OAuth
Apps** with:

```text
Homepage URL: https://jamesonthehill.com/Socratic-Chat/
Authorization callback URL: https://socratic-chat-api.onrender.com/api/auth/github/callback
```

Add the generated credentials to Render and enable the requirement only after
both values are present:

```text
GITHUB_CLIENT_ID=YOUR_GITHUB_OAUTH_CLIENT_ID
GITHUB_CLIENT_SECRET=YOUR_GITHUB_OAUTH_CLIENT_SECRET
REQUIRE_GITHUB_ACCOUNT=true
GITHUB_CALLBACK_URL=https://socratic-chat-api.onrender.com/api/auth/github/callback
FRONTEND_URL=https://jamesonthehill.com/Socratic-Chat/
```

The authorization request includes `user:email`. The callback lists the user's
GitHub emails and requires a verified `@charlotte.edu` address. Each GitHub
numeric user ID can be linked to only one school account, and protected APIs
require the resulting signed application session.

## Keeping a teaching example consistent

The tutor keeps the first explicit scenario (for example, an opening beginning
with “Imagine” or “Suppose”) from the saved conversation available to generation
and answer evaluation, alongside the recent eight-message exchange. It recovers
that example even after it leaves the recent-message window or a chat is resumed.
An explicit request such as “use a different example” resets the example.

Hints and corrections simplify the same people, objects, and goal. Evaluated
misconceptions trigger a counterexample within that situation; partial answers
lead to a missing connection; supported reasoning leads to a why/what-if question.
The tutor no longer advances to synthesis or reflection merely because a fixed
number of questions has been asked. Once the existing mastery checks indicate
readiness, it asks a signposted transfer problem that changes one condition of
the same example. A claim such as “I understand” still needs demonstrated evidence.

Scenario continuity is a model instruction supported by retained context and
scenario-aware fallback questions; it is not a guarantee that every generated
response will stay on topic. The existing course-grounding checks still apply.
