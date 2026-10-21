"""Course-scoped ingestion and retrieval through the SDL document pipeline."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx
from fastapi import HTTPException
from app import db, settings
from app.chunking import CHUNKING_VERSION, chunk_document
from app.rag import EmbeddingError, chunk_text, create_embeddings, read_pdf_pages


def pipeline(method, path, **kwargs):
    token = os.getenv("PLATFORM_SERVICE_TOKEN", "")
    if not token:
        raise HTTPException(503, "Configure the shared document service credentials.")
    try:
        with httpx.Client(timeout=180, headers={"X-Platform-Service": token}) as client:
            response = client.request(method, os.getenv("SELF_DIRECTED_LEARNING_URL", "http://127.0.0.1:8100").rstrip("/") + path, **kwargs)
        if response.is_error:
            if response.status_code in {401, 403}:
                raise HTTPException(503, "The shared document service credentials are not configured correctly.")
            try:
                detail = response.json().get("detail")
            except (AttributeError, ValueError):
                detail = None
            raise HTTPException(response.status_code if response.status_code < 500 else 502, detail or "The shared document service could not complete this action.")
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "The shared document service is unavailable. Your selection has been retained.") from exc


def embedding_options():
    return {"model": settings.embedding_model_name(), "dimensions": settings.EMBEDDING_DIMENSIONS}


def _parse_pdf(filename, content):
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("document" + Path(filename).suffix.lower())
        path.write_bytes(content)
        chunks = []
        for page_number, page_text in read_pdf_pages(path):
            chunks.extend(
                {
                    "text": f"Page {page_number}: {text}",
                    "position": len(chunks),
                    "page_number": page_number,
                    "metadata": {"page_numbers": [page_number]},
                }
                for text in chunk_text(page_text)
            )
    if not chunks:
        raise HTTPException(422, "This PDF has no extractable text. Upload a text-based PDF or use OCR for scanned pages.")
    return chunks


def _parse_html(filename, content):
    # Uploaded HTML already has a semantic, section-aware parser in Socratic Chat.
    # Parse it here so indexing does not depend on the separate SDL service.
    document = content.decode("utf-8-sig", errors="replace")
    chunks = [
        {
            "text": chunk.text,
            "position": position,
            "metadata": {
                "section_path": list(chunk.section_path),
                "assignment_number": chunk.assignment_number,
                "chunk_profile": chunk.profile,
                "approximate_token_count": chunk.token_count,
                "chunking_version": CHUNKING_VERSION,
            },
        }
        for position, chunk in enumerate(chunk_document(filename, document, source_format=Path(filename).suffix))
    ]
    if not chunks:
        raise HTTPException(422, "This HTML file has no readable text to index.")
    return chunks


def ingest(course_id, account, filename, content_type, content):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        chunks = _parse_pdf(filename, content)
    elif suffix in {".html", ".htm"}:
        chunks = _parse_html(filename, content)
    else:
        chunks = pipeline("POST", "/internal/platform/rag/parse", files={"file": (filename, content, content_type)})["chunks"]
    try:
        vectors = create_embeddings([c["text"] for c in chunks])
    except EmbeddingError as exc:
        raise HTTPException(503, str(exc)) from exc
    document_id = str(uuid4())
    # Persist only after successful parsing and embedding. Clean up a failed index write.
    file_id = db.save_rag_file(filename, content_type, content, user_id=str(account["user_id"]), course_id=str(course_id), document_id=document_id)
    try:
        db.replace_document_chunks(file_id, document_id, filename, chunks, vectors, settings.embedding_model_name(), course_id=str(course_id))
    except Exception:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id=%s", (file_id,))
        raise
    return {"id": file_id, "file_id": file_id, "document_id": document_id, "name": filename, "size": len(content), "chunk_count": len(chunks)}


def course_chunks(course_id, document_ids):
    available = {str(f["document_id"]) for f in db.list_rag_files(limit=100000, course_id=str(course_id)) if f.get("document_id")}
    if not set(document_ids).issubset(available):
        raise HTTPException(422, "Select documents belonging to this course.")
    return db.snapshot_document_chunks(str(course_id), document_ids) if document_ids else []


def search(course_id, document_ids, query, limit):
    chunks = course_chunks(course_id, document_ids)
    return pipeline("POST", "/internal/platform/rag/search", json={"query": query, "chunks": chunks, "limit": limit, **embedding_options()})
