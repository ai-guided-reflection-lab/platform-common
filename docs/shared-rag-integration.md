# Shared course document pipeline

Other chat teams can retrieve the same course chunks used by the platform's SDL. Call the common platform API with the signed-in user's bearer token. The platform checks that the user belongs to the requested course and that every document ID belongs to that course. Do not pass the internal `PLATFORM_SERVICE_TOKEN` to a browser or chatbot client.

The instructor uploads documents once from the course's Document Library. The SDL pipeline parses the file, requests embeddings, and stores the original file in `shared_rag.documents` and chunk metadata and vectors in `shared_rag.chunks`. Activities select indexed documents by `document_id`. These are shared resources for every chatbot.

`SHARED_RAG_DB_SCHEMA` defaults to `shared_rag`. Existing `socratic_chat.rag_files_socratic_chat` and `socratic_chat.document_chunks_socratic_chat` tables are moved and renamed transactionally during database initialization. Their rows, IDs, embeddings, foreign keys, and indexes are preserved. Initialization refuses to merge two existing stores implicitly.

On October 16, 2026, the approved RAG table migration was applied to Supabase project `inivtfjnjuxqucegbych`. All 11 existing documents and 78 chunks were preserved, with local row backups excluded from Git. The supplied `split_presentations_1.pptx` and its 21 locally indexed chunks were then copied into a private Supabase test course. A fresh connection retrieved all 21 chunks and pgvector returned three nearest matches. Totals during testing: 12 documents and 99 chunks. The private test course and its presentation were subsequently removed at the user's request; the retained totals are the original 11 documents and 78 chunks. This verifies database persistence and retrieval; it does not establish that the running local UI writes to Supabase. Other platform migrations and the full assignment journey remain separate checks. Backends using the old table names must be updated with the shared-schema code.

For teammates using a dedicated read-only database login:

```sql
SELECT document_id, course_id, chunk_index, title,
       page_number, chunk_text, metadata, embedding_model, embedding
FROM shared_rag.chunks
WHERE course_id = '<course-uuid>'
ORDER BY document_id, chunk_index;
```

Grant that login `USAGE` on schema `shared_rag` and `SELECT` on `shared_rag.chunks`; the shared retrieval API below can also enforce course membership for callers.

## Retrieve ranked chunks

```http
POST /api/platform/rag/search
Authorization: Bearer <signed-in-platform-access-token>
Content-Type: application/json

{
  "course_id": "<course-uuid>",
  "document_ids": ["<document-uuid>"],
  "query": "What are the stakeholder requirements?",
  "limit": 5
}
```

Response:

```json
{
  "chunks": [
    {
      "text": "...",
      "title": "requirements-guide.pdf",
      "document_id": "<document-uuid>",
      "page_number": 4,
      "metadata": {}
    }
  ]
}
```

The search result omits embeddings. Each chunk retains its source document and parser metadata so the chat can cite the title and page.

## Read chunks in document order

Use this when a chat needs to process every chunk. Paginate with `next_offset` until it is `null`:

```http
POST /api/platform/rag/chunks
Authorization: Bearer <signed-in-platform-access-token>
Content-Type: application/json

{
  "course_id": "<course-uuid>",
  "document_ids": ["<document-uuid>"],
  "offset": 0,
  "limit": 200
}
```

The response contains `chunks`, `total`, and `next_offset`. It does not include embeddings. Keep the same course and document IDs for subsequent pages. The API enforces membership and scope on every request.

## Python example

```python
import httpx

def search_course_documents(platform_url, access_token, course_id, document_ids, query):
    response = httpx.post(
        f"{platform_url.rstrip('/')}/api/platform/rag/search",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "course_id": course_id,
            "document_ids": document_ids,
            "query": query,
            "limit": 5,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["chunks"]
```

## Access and availability

The student's existing platform session authorizes access. Instructors who own the course can use the same API. A course member can retrieve only documents selected from that course; guessed document IDs from another course are rejected. The internal SDL parser, embedder, and ranking endpoints require `X-Platform-Service` and must only be called by the trusted platform service.

Uploads remain unavailable to retrieval until the configured embedding provider successfully creates vectors. The current OpenAI credential returns HTTP 401, so live indexing and semantic search need a valid server-side `OPENAI_API_KEY`. The platform returns the provider failure to the instructor and removes any partially persisted batch; it does not invent fallback vectors.
