# Adaptive Learning — standalone Self-Directed Learning

This directory runs the Self-Directed Learning work independently from ClubALL, Socratic Chat, and Reflections. It contains two separate interfaces backed by one standalone API:

- Instructor studio: `http://127.0.0.1:5173`
- Student workspace: `http://127.0.0.1:5174`
- API documentation: `http://127.0.0.1:8100/docs`

## First-time setup

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r adaptive-learning-app\backend\requirements.txt
cd adaptive-learning-app\instructor-app
npm install
cd ..\student-app
npm install
```

The API reads the workspace root `.env`, so the existing `OPENAI_API_KEY` can be reused. Optional standalone overrides can be placed in `adaptive-learning-app/.env`; see `.env.example`.

## Run locally

### PDF indexing

PDF uploads are indexed with Docling's structured PDF pipeline, its PDFium
backend, and HybridChunker. The PDFium backend avoids Windows renderer access
violations observed with the default threaded backend on the scanned fixture.
`PDF_CHUNK_MAX_TOKENS` defaults to 512 and uses the existing OpenAI embedding
model's tokenizer. Contextualized chunk text is both embedded and stored;
small JSON metadata retains physical page numbers and available headings/title.
Existing TXT/Markdown chunking and top-four cosine retrieval are unchanged.
Instructor PDF preview still uses pypdf and the existing 30,000-character limit.

The pinned backend dependencies include PDF-only Docling components and RapidOCR
with ONNX Runtime. OCR is enabled without forcing full-page OCR. Layout/table/OCR
models may download on first use; provision their caches before demonstration or
offline deployment. `PDF_MODEL_ARTIFACTS_PATH` can point at prefetched Docling
artifacts (see Docling's model provisioning documentation). PPTX and explicit URL
resources use the Stage 3 paths described below. Existing indexed documents are not automatically
reparsed. Database initialization adds `chunks.metadata` with an empty JSON
default for older rows on SQLite and PostgreSQL.

Run the backend regression and PDF fixture tests from `adaptive-learning-app/backend`:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests -q
```

The PDF tests exercise real local parsing/OCR/table models but mock embeddings;
they do not require OpenAI API calls. A cold model cache requires network access.

Open three terminals:

```powershell
cd adaptive-learning-app\backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8100
```

```powershell
cd adaptive-learning-app\instructor-app
npm run dev
```

```powershell
cd adaptive-learning-app\student-app
npm run dev
```

After dependencies are installed, `adaptive-learning-app\start.ps1` starts all three processes using the shared `DATABASE_URL` from the root `.env`. SDL stores its tables in `SELF_DIRECTED_LEARNING_DB_SCHEMA` (default `self_directed_learning`), alongside the platform, Socratic, and Reflections schemas. Pass `-UseLocalSQLite` only for an explicit offline session. `-UseConfiguredDatabase` remains accepted for compatibility and selects the shared database.

## Demo flow

1. Open the student workspace and choose Alex or Jordan. The configured Requirements Engineering sample is available in a fresh local database.
2. Open a lesson for the personalized greeting, short introduction, concrete example, objectives, and one familiarity question.
3. Study the approved links, ask for examples or help, then select **I am done** or send a readiness reply.
4. Answer five MCQs, one at a time. Report confidence on each and explain questions 4 and 5. Missing details, hints, and “I don't know” are supported.
5. See the score out of five and a targeted follow-up. Work through fresh examples and independent checks; confidence does not change the quiz score.
6. Reflect on what you can do now, then choose another example, a challenge, a recap, or a pause. The session stays open and progress is saved.
7. The instructor studio shows the original diagnostic evidence, confidence, explanations, assistance, practice revisions, and reflections.

For a new topic, upload a PDF, Markdown, or text document and click **Review**. A configured AI provider derives the topic, objectives, difficulty, prerequisites, five diagnostic questions, explanations, examples, practice rubrics, and reflection from the document. Educational reading links are checked before inclusion. The review displays the complete prepared lesson and the document's indexed chunk count. **Publish** sits at the bottom and approves the reviewed content for the selected students. Incomplete generated lessons remain drafts; published lessons are read-only.

Set `ADAPTIVE_AI_MODE=demo` for offline use. Local assessment follows explicit professor-authored phrase groups and is approximate. Live semantic assessment requires the configured provider. Set `ADAPTIVE_DATABASE_PATH` to the absolute local SQLite path if your workspace environment points to a remote database that is unavailable.

See [the exact student flow](docs/student-learning-flow.md) for stage behavior and assessment limits. The latest flow is version 2; existing version 1 lessons and student work remain intact.

## Integration boundary

### Corrected process-memory lesson

`backend/lessons/operating-system-processes.json` contains the corrected configuration from the local Operating System Processes lesson. Network-buffer evidence requires both identifying the buffer and explaining its exclusion; standard and accelerated follow-ups now test memory sections rather than process states. It is an unapproved draft for instructor review.

Create a **new assignment** with this file as the `learning_plan` using the existing instructor assignment API, review/approve the content, then publish it for new sessions. Do not overwrite an existing published assignment or its attempts. Existing sessions intentionally retain their immutable lesson snapshots and previous results; loading or resuming them does not apply this data correction retroactively. No database migration is needed.

The standalone app owns its learning plans, tutoring flow, evidence, progress, and local RAG. Its current `X-Demo-User` identity and SQLite persistence are standalone adapters. A later ClubALL adapter can replace identity, course enrollment, assignments, and persistence while keeping the Self-Directed Learning workflow and both role-specific interfaces intact.

## PowerPoint and URL resources (Stage 3)

The existing document upload and preview accept `.pptx` and `.ppt` as well as
PDF, Markdown, and text. PPTX is read with `python-pptx`: ordinary slides produce
one chunk, oversized slides split within the slide, and every piece retains its
slide number/title. Bullet levels, table headers/rows, and existing speaker notes
are included. Images, charts, animations, and visual diagrams are not transcribed.
Legacy PPT requires LibreOffice (`soffice`/`libreoffice` on PATH or a standard
Windows installation); otherwise the API returns a clear 503 asking for PPTX.
Conversion uses a temporary isolated profile and a 60-second timeout. LibreOffice
is optional and is not installed automatically by the application or Dockerfile.

On a saved draft's review screen, **Add URL resource** explicitly indexes one
public article or PDF through
`POST /api/instructor/assignments/{assignment_id}/documents/url` with
`{"url":"https://university.edu/article"}`. Existing instructor ownership and
draft-only restrictions apply. Adding a resource augments RAG knowledge; it does
not regenerate or change an approved lesson. Discovered study links are never
automatically indexed. The document list uses the extracted title or URL basename.

URL downloads accept HTTP/HTTPS on standard ports, reject credentials and known
video/social hosts, validate DNS addresses before each request/redirect, disable
environment proxies, limit redirects to five, and bound decoded content to 10 MB.
Network operations use a 20-second timeout with an elapsed-time budget checked
during downloading. Public HTML articles use Trafilatura's structured extraction
without comments; headings, paragraphs, lists, and tables form section-aware
chunks. An actual PDF signature selects the **unchanged** Docling/HybridChunker
PDF path, even for extensionless URLs. Source and final URLs are stored in chunk
metadata. Fetch/parse/index failures roll back records and remove saved files.

`RESOURCE_CHUNK_MAX_TOKENS=512` controls slide/HTML chunks including repeated
context; PDF retains its separate `PDF_CHUNK_MAX_TOKENS` setting. All formats use
the same `ResourceChunk(content, position, metadata)` representation and existing
embedding, database, cosine ranking, and top-four retrieval. No migration is needed.
Examples of stored metadata:

```json
{"source_type":"pptx","slide":12,"title":"Process States"}
{"source_type":"html","title":"Process Management","section":"Ready processes","source_url":"https://university.edu/start","final_url":"https://university.edu/article"}
{"source_type":"pdf","pages":[4],"source_url":"https://university.edu/download","final_url":"https://university.edu/paper.pdf"}
```

This is static single-page ingestion, not crawling or browser rendering. Private,
authenticated, video/social, and arbitrary binary resources are unsupported. DNS
validation is a practical guard, not an egress firewall: deployments handling
untrusted URLs should also restrict private-network access at the network level
to cover DNS rebinding. JavaScript-only pages and unreliable table extraction may
require a downloadable PDF/PPTX. These extensions remain deferred.

## Resource ingestion

The production routes have one common boundary:

```text
PDF upload -> ingest_resource -> ingest_pdf (Docling + HybridChunker) --+
PPTX upload -> ingest_resource -> ingest_pptx (slide-aware) ------------+
HTML URL -> fetch_resource_url -> ingest_html (Trafilatura) ------------+-> ResourceChunk
PDF URL -> fetch_resource_url -> ingest_resource -> same ingest_pdf ---+       |
                                                                   rag.py: embed_texts
                                                                          -> atomic DB insert
                                                                          -> retrieve
```

`main.py` authenticates the instructor, checks assignment ownership and draft
status, and calls `rag.add_document()` or `rag.add_url_document()`. `rag.py`
coordinates parsing, calls the existing provider embedding helper once with all
chunk texts, and inserts the document/chunks in one database transaction. Failures
remove the saved input and roll back database inserts. `resource_ingestion.py`
does parsing/fetching only: it does not embed or write database records.

### Using the Ingestion Layer

1. **Submit:** for authenticated instructor clients, POST multipart `file` to
   `/api/instructor/assignments/{assignment_id}/documents`, or JSON
   `{"url":"https://university.edu/article"}` to the same path plus `/url`.
   Both return HTTP 201 with `{"id":document_id,"filename":display_name,"chunk_count":N}`.
   Use the application's existing identity headers; these resources are draft-only.
   Internal authorized callers can `await rag.add_document(assignment_id, UploadFile)`
   or `await rag.add_url_document(assignment_id, url)` for the same indexing result.
   These internal functions do not authorize access themselves.
2. **Formats:** PDF, PPTX, public HTML/PDF URLs; existing TXT/Markdown remain
   supported. PPT is conditional on an installed LibreOffice executable.
3. **Parsing-only return:** `ingest_resource(path: pathlib.Path)` handles PDF,
   PPTX, or PPT and returns `list[ResourceChunk]`. It does not accept a URL or
   TXT/Markdown. For a URL without indexing, `fetch_resource_url(url: str)`
   returns `(bytes, detected_content_type, final_url)`; after saving those bytes,
   use `ingest_html(path, source_url, final_url)` for HTML or `ingest_resource(path)`
   for PDF, adding `source_url`/`final_url` metadata as `rag.py` does. Temporary
   file ownership/cleanup belongs to that caller. The actual common representation is:

   ```python
   @dataclass
   class ResourceChunk:
       content: str
       position: int
       metadata: dict
   ```

4. **Metadata:** `position` is zero-based within a resource; PPTX `slide` and PDF
   `pages` are one-based. Structured chunks guarantee `source_type`; PPTX also
   guarantees `slide`. URL chunks guarantee `source_url` and `final_url`. PDF
   `pages`, extracted `title`, and `section` are present only when available.
   TXT/Markdown and migrated old chunks may have `{}`. Do not require optional keys.

   ```json
   {"source_type":"pdf","pages":[12],"section":"Process Management"}
   {"source_type":"pptx","slide":8,"title":"Process States"}
   {"source_type":"html","section":"Ready Processes","source_url":"https://university.edu/article","final_url":"https://university.edu/article"}
   {"source_type":"pdf","pages":[4],"source_url":"https://university.edu/download","final_url":"https://university.edu/paper.pdf"}
   ```

5. **Identify:** the indexing result's `id` is the existing `documents.id`.
   Parsing-only chunks have no resource ID; storage associates them with that
   document. Use returned `document_id` plus `position` to identify a stored chunk.
6. **Retrieve:** `rag.retrieve(assignment_id: str, query: str, limit: int = 4)`
   embeds the query and returns dictionaries with `document_id`, `filename`,
   unchanged `content`, `position`, decoded `metadata`, and cosine `score` rounded
   to four decimals. Assignment filtering precedes unchanged cosine ranking.
   Metadata and position are additive fields introduced during Stage 4; existing
   lesson citations still show one source per document. Use the retrieval list
   directly when every retrieved page/slide matters. Authorize the assignment
   before calling this internal function; it is not a public retrieval endpoint.
7. **Errors:** API/coordinator callers handle 401/403/404 for identity/access,
   409 for frozen assignments, 413 for oversized uploads, 422 for invalid or
   unreadable resources (including URL timeout/size/safety failures), 503 for
   unavailable parsing dependencies or LibreOffice, 502 for embedding failures,
   and 500 for storage failures. Parsing-only calls can raise `ResourceIngestionError`
   (`ValueError`), its `PowerPointConversionUnavailable` subclass, `ImportError`,
   or parser-specific exceptions; prefer the coordinator/API if you need normalized
   errors without knowing library internals. Retrieval/provider errors propagate
   to its caller. Duplicate explicit submissions intentionally create separate
   document IDs; there is no automatic deduplication or idempotency guarantee.

### Audit decisions and remaining limits

PDF indexing and the PDF HybridChunker configuration remain unchanged. PDF preview
still uses pypdf, with a 30,000-character response limit. This avoids loading OCR,
layout/table models for previews, but scanned-only PDFs cannot seed the quick
lesson-creation flow; upload them to an existing draft for OCR indexing, or supply
a selectable-text export. Missing preview dependencies now report 503 consistently.
Preview and indexing are separate requests and may parse the same input twice;
each indexing request parses once and batches its embeddings once. Docling's
converter is cached per process and conversion is serialized, not initialized per
chunk. Input/download buffers are bounded to 10 MB; no queues or new caching layers
were added. Cold model initialization/downloads can still delay the first PDF.

URL requests use the remaining download budget across redirects, check elapsed
time after headers and every decoded transport block, and close responses on
failure. This fixes the buffered slow-stream gap. The 20-second download budget
is not a hard wall-clock limit for OS DNS resolution, parsing, or embedding.
DNS rebinding remains possible; use network egress restrictions for untrusted
deployments. Static article extraction and slide text do not capture JavaScript
rendering, images, or charts. LibreOffice conversion is unavailable locally and
has only a mocked routing test here; no live PostgreSQL or Docker runtime test
was performed. Runtime auth remains the application's existing demo adapter.

Future improvements (deferred): optional deduplication/idempotency, a consistent
OCR preview workflow if scanned-only authoring becomes necessary, and deployment
validation with LibreOffice/PostgreSQL/network egress restrictions. No format,
retrieval, grading, reflection, Socratic, or lesson-flow expansion is included.

## Verification commands

Instructor component tests live in `platform_frontend` (the standalone instructor
package has no separate test runner). Its full suite also covers student/platform
regressions. The handoff tests use real PDF/PPTX/HTML parsing and mocked URL/provider
traffic; they do not require OpenAI API calls.

```powershell
cd adaptive-learning-app\backend
..\..\.venv\Scripts\python.exe -m pytest tests -q
..\..\.venv\Scripts\python.exe -m pytest tests/test_ingestion_handoff.py -q

cd ..\instructor-app
npm run build -- --configLoader runner

cd ..\student-app
npm run build -- --configLoader runner

cd ..\..\platform_frontend
npm test
npm test -- --run src/instructor-document-flow.test.jsx
npm run build
```
