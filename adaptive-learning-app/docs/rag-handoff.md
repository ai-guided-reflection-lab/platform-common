# SDL RAG handoff for the Socratic and Reflections owners

This PR supplies the SDL RAG service. It does not modify either chat application,
enable a platform-wide RAG override, or route their existing uploads through SDL.
Each application's owner performs that wiring in a separate change.

## Service configuration

Run the SDL backend with its backend requirements installed. Configure
`OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`),
`ADAPTIVE_AI_MODE=openai` or an available hosted chat mode, and
`PLATFORM_SERVICE_TOKEN`. Consumers use `SELF_DIRECTED_LEARNING_URL` as the base
URL and the same service token. In Docker the base URL is
`http://self-directed-learning:8100`; on the local launcher it is
`http://127.0.0.1:8100`.

All endpoints below require `X-Platform-Service: <token>`. Call them from your
backend only. Keep that token and the provider API key out of browser code.

## Endpoints

| Endpoint | Request | Response |
| --- | --- | --- |
| `POST /internal/platform/rag/parse` | Multipart `file`, with its original filename and extension; maximum 10 MB | `chunks`: text, position, metadata, page_number |
| `POST /internal/platform/rag/embeddings` | JSON `texts`, `model`, `dimensions` | Ordered `embeddings`, plus `model` |
| `POST /internal/platform/rag/search` | JSON `query`, `chunks`, `limit`, `model`, `dimensions` | Ranked `chunks`, with `score`; embedding arrays omitted |

Parsing supports PDF, PPTX, PPT, DOCX, text, Markdown, HTML, and LaTeX. PPT files
require LibreOffice conversion; use PPTX if that dependency is unavailable.
PDF parsing uses Docling. Embedding requests are batched by SDL and preserve
the requested vector dimensions. Service requests require real vectors of the
configured dimension; offline/demo vectors cannot replace a hosted course index.

Example embedding request:

```json
{"texts":["A functional requirement describes system behavior."],"model":"text-embedding-3-small","dimensions":1536}
```

For search, each supplied chunk must contain `embedding` as a numeric array.
Preserve your own identifiers and citation fields alongside it, for example:

```json
{"query":"What is a functional requirement?","limit":4,"model":"text-embedding-3-small","dimensions":1536,"chunks":[{"document_id":"doc-id","chunk_id":"chunk-id","course_id":"course-id","title":"Course notes","text":"A functional requirement describes system behavior.","embedding":["replace with the numeric vector returned by /embeddings"]}]}
```

The embedding in this example is illustrative: replace it with the full numeric
array before making the request. The service ranks only the supplied chunks; it
does not load another application's database or select the authorized course.

## What each owner needs to implement

1. Keep your existing upload authentication, course permissions, and size checks.
   Forward an authorized uploaded file to `/parse`.
2. Send parsed chunk texts to `/embeddings`, using the model and dimension that
   match your existing database index. Store the text, embedding, original file,
   and citation metadata using your application's existing persistence layer.
3. On a chat turn, select only chunks authorized for that student/course or
   published assignment snapshot. Convert database vectors to numeric arrays
   and call `/search`. Do not send an entire cross-course index.
4. Map the returned chunk fields to your application's source/citation model.
   Your team owns how excerpts enter prompts and how citations appear in chat.
5. Preserve your existing behavior for service outages and publish validation.
   Handle 401 (service token), 409 (model mismatch), 413 (file size),
   422 (invalid data), and 503 (unavailable parser/embedding provider).

Keep embedding models and dimensions consistent between indexing and search.
Changing either requires reindexing affected documents. The service does not
automatically migrate existing indexes or modify either chat's database.

## Acceptance checks for the owners' follow-up PRs

- Upload a document through the real course interface and verify saved chunks.
- Ask a grounded question and verify the returned citation matches the upload.
- Verify another student/course cannot retrieve those chunks.
- Verify immutable published snapshots still work after a source is changed.
- Check that a service outage is surfaced without losing an upload or response.
