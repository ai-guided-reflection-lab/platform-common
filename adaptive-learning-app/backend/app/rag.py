from __future__ import annotations

import json
import math
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from .config import UPLOAD_DIR
from .db import connection, now
from .openai_client import embed_texts


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise HTTPException(503, "Install pypdf to upload PDF files.") from exc
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8", errors="replace")


def split_text(text: str, size: int = 1100, overlap: int = 180) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            boundary = clean.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)
    return chunks


async def add_document(assignment_id: str, upload: UploadFile) -> dict:
    suffix = Path(upload.filename or "document").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(422, "Upload a PDF, Markdown, or text file.")
    document_id = str(uuid4())
    safe_name = f"{document_id}{suffix}"
    path = UPLOAD_DIR / safe_name
    content = await upload.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Documents must be 10 MB or smaller.")
    path.write_bytes(content)
    text = extract_text(path)
    chunks = split_text(text)
    if not chunks:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "No readable text was found in this document.")
    embeddings = embed_texts(chunks)
    with connection() as conn:
        conn.execute(
            "INSERT INTO documents(id,assignment_id,filename,content_type,path,created_at) VALUES (?,?,?,?,?,?)",
            (document_id, assignment_id, upload.filename or safe_name, upload.content_type or "application/octet-stream", str(path), now()),
        )
        conn.executemany(
            "INSERT INTO chunks(id,document_id,position,content,embedding) VALUES (?,?,?,?,?)",
            [
                (str(uuid4()), document_id, index, chunk, json.dumps(vector))
                for index, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True))
            ],
        )
    return {"id": document_id, "filename": upload.filename, "chunk_count": len(chunks)}


def _cosine(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if not size:
        return 0.0
    dot = sum(left[i] * right[i] for i in range(size))
    lnorm = math.sqrt(sum(left[i] ** 2 for i in range(size)))
    rnorm = math.sqrt(sum(right[i] ** 2 for i in range(size)))
    return dot / (lnorm * rnorm) if lnorm and rnorm else 0.0


def retrieve(assignment_id: str, query: str, limit: int = 4) -> list[dict]:
    vector = embed_texts([query])[0]
    with connection() as conn:
        rows = conn.execute(
            """SELECT c.content,c.embedding,d.id AS document_id,d.filename
               FROM chunks c JOIN documents d ON d.id=c.document_id
               WHERE d.assignment_id=?""",
            (assignment_id,),
        ).fetchall()
    ranked = sorted(
        ({**dict(row), "score": _cosine(vector, json.loads(row["embedding"]))} for row in rows),
        key=lambda item: item["score"],
        reverse=True,
    )[:limit]
    return [
        {"document_id": item["document_id"], "filename": item["filename"], "content": item["content"], "score": round(item["score"], 4)}
        for item in ranked
    ]
