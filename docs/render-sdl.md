# Add SDL and shared documents to an existing Render deployment

The platform and Reflections services do not start SDL. Deploy one additional backend for both the SDL workflow and shared document parsing, embeddings and retrieval.

## Existing Platform and Reflections services

Create a **Web Service** in Render using this repository and branch `platform-ui-rework` (or `main` after merging). Select **Docker**.

| Setting | Value |
| --- | --- |
| Root Directory | Leave empty |
| Dockerfile Path | `adaptive-learning-app/backend/Dockerfile` |
| Docker Build Context Directory | `adaptive-learning-app/backend` |
| Docker Command | Leave empty; the image respects Render's `PORT` |
| Health Check Path | `/api/health` |

Set these environment variables on the **new SDL service**:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Copy the existing platform's Supabase connection string privately |
| `PLATFORM_SERVICE_TOKEN` | Copy the existing platform's exact value; do not generate a different one |
| `SELF_DIRECTED_LEARNING_DB_SCHEMA` | `self_directed_learning`, or the SDL schema already used by this deployment |
| `ADAPTIVE_PLATFORM_ONLY` | `true` |
| `ADAPTIVE_DATA_DIR` | `/tmp/sdl-data` |
| `LLM_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | Valid provider key, entered only in Render's environment settings |

Leave `ADAPTIVE_DATABASE_PATH` unset so saved lessons and attempts use PostgreSQL rather than a temporary SQLite file. Configure `OPENAI_EMBEDDING_MODEL` consistently with the platform (default `text-embedding-3-small`). Native PDF/OCR model dependencies are included; models may download on first PDF ingestion. The image uses CPU-only PyTorch.

Deploy, then open `https://YOUR-SDL-SERVICE.onrender.com/api/health`. It must return HTTP 200. An unauthenticated request to `/api/student/assignments` must return HTTP 401; this confirms the platform-only guard is active. Do not add the service token to a URL or frontend build configuration.

On the **existing platform service**, set:

```env
SELF_DIRECTED_LEARNING_URL=https://YOUR-SDL-SERVICE.onrender.com
```

Use only the service origin: no `/api`, `/platform`, or trailing assignment path. Save and redeploy the platform. `localhost:8100` and Docker Compose service names cannot reach a separate Render web service.

The standalone `render.sdl.yaml` Blueprint describes only this additional service. Use it instead of the full `render.yaml` if the existing services were created manually or have different names. The full Blueprint references Platform and Reflections by their own Blueprint names; it is intended for deploying the complete stack together.

## Verify the whole connection

1. Sign in as an instructor on the platform, open a course-context activity, and upload a small `.txt` document first.
2. Confirm it appears in Existing documents and can be selected. Check the configured shared RAG schema in Supabase for its document and chunk records.
3. Select SDL, enter the learning focus, and choose Review activity. Inspect the generated lesson before publishing.
4. Open the published activity as its assigned student. Confirm the lesson resumes and a reply is saved.

If the platform still reports the document service is unavailable, check the SDL service is live, its health URL responds, and the platform's URL is correct. A service-token mismatch has a separate credentials error. Embedding authentication/quota errors require checking the SDL service's provider key and quota.

Free services can sleep; PDF/OCR model startup also consumes more resources than text/PPTX parsing. If Render logs show an out-of-memory termination, choose an instance with sufficient RAM before testing PDFs. Do not reset the database to resolve service connectivity.

## Local image verification

The Docker image built successfully and started with `PORT=10000`. Checks passed for health, unauthenticated API rejection, authenticated TXT/PPTX/DOCX parsing, CPU-only PyTorch, PDF parser imports, and `pip check`. The disposable container used SQLite and synthetic documents; no real database or provider credentials were passed to it. These checks do not verify deployed Supabase writes, live embeddings, or a complete PDF/OCR conversion. Test those after setting the Render environment.
