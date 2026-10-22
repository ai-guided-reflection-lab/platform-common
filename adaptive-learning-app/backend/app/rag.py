from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from uuid import uuid4
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, unquote

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from .config import UPLOAD_DIR
from .db import connection, now
from .openai_client import embed_texts
from .resource_ingestion import (ResourceChunk, ingest_resource, ingest_html, fetch_resource_url,
                                 ResourceIngestionError, PowerPointConversionUnavailable)


logger = logging.getLogger(__name__)


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".pptx", ".ppt", ".tex", ".html", ".htm", ".docx"}


def extract_text(path: Path) -> str:
    if path.suffix.lower() in {".docx", ".html", ".htm", ".tex"}:
        return "\n\n".join(chunk.content for chunk in parse_resource(path))
    if path.suffix.lower() in {".pptx", ".ppt"}:
        return "\n\n".join(chunk.content for chunk in ingest_resource(path))
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise HTTPException(503, "Install pypdf to upload PDF files.") from exc
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8", errors="replace")


async def preview_document(upload: UploadFile) -> dict:
    suffix = Path(upload.filename or "document").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(422, "Upload a PDF, PowerPoint, Markdown, or text file.")
    content = await upload.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Documents must be 10 MB or smaller.")
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("preview" + suffix)
        path.write_bytes(content)
        try:
            text = (await run_in_threadpool(extract_text, path)).strip()
        except HTTPException:
            raise
        except PowerPointConversionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except ResourceIngestionError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ImportError as exc:
            raise HTTPException(503, "Resource processing dependencies are unavailable.") from exc
        except Exception as exc:
            if suffix in {".pptx", ".ppt"}:
                raise HTTPException(422, "The presentation could not be read. Upload a valid, unencrypted PPTX or PPT file.") from exc
            raise HTTPException(422, "The document could not be read. Upload a readable PDF, text, or Markdown file.") from exc
    if not text:
        raise HTTPException(422, "No readable text was found. For a scanned PDF, first export a version with selectable text.")
    return {"filename": upload.filename, "text": text[:30000], "truncated": len(text) > 30000}


async def preview_url_document(url: str) -> dict:
    """Use the same validated downloader and parsers as URL indexing."""
    try:
        content, content_type, final_url = await run_in_threadpool(fetch_resource_url, url)
        suffix = ".pdf" if content_type == "application/pdf" else ".html"
        with TemporaryDirectory() as directory:
            path = Path(directory) / ("preview" + suffix)
            path.write_bytes(content)
            chunks = await run_in_threadpool(ingest_resource, path) if suffix == ".pdf" else await run_in_threadpool(ingest_html, path, url, final_url)
        text = "\n\n".join(chunk.content for chunk in chunks).strip()
        if not text:
            raise ResourceIngestionError("No readable resource content was found.")
        filename = next((chunk.metadata["title"] for chunk in chunks if chunk.metadata.get("title")), final_url)[:300]
        return {"filename": filename, "text": text[:30000], "truncated": len(text) > 30000}
    except ResourceIngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503, "Resource processing dependencies are unavailable.") from exc
    except Exception as exc:
        raise HTTPException(422, "The URL resource could not be read. Use a public HTML article or unencrypted PDF.") from exc


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


def parse_resource(path: Path) -> list[ResourceChunk]:
    """One parsing/chunking pipeline for SDL and the common course library."""
    suffix = path.suffix.lower()
    if suffix in {".pdf", ".pptx", ".ppt"}:
        return ingest_resource(path)
    if suffix in {".html", ".htm"}:
        return ingest_html(path, "", "")
    if suffix == ".docx":
        from docx import Document
        from docx.text.paragraph import Paragraph
        document = Document(path)
        blocks = []
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                blocks.append(block.text)
            else:
                blocks.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
        text = "\n".join(blocks)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".tex":
            import re
            text = re.sub(r"(?<!\\)%[^\n]*", "", text)
            text = re.sub(r"\\(?:documentclass|usepackage|begin|end)\{[^}]*\}", " ", text)
            text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^]]*\])?", " ", text)
            text = text.replace("{", " ").replace("}", " ")
    return [ResourceChunk(chunk, index, {"source_type": "docx"} if suffix == ".docx" else {}) for index, chunk in enumerate(split_text(text))]


def rank_chunks(chunks: list[dict], vector: list[float], limit: int = 4) -> list[dict]:
    """The shared SDL cosine retriever; never compare different vector spaces."""
    if any(len(item["embedding"]) != len(vector) for item in chunks):
        raise HTTPException(409, "These documents use a different embedding space. Reindex the course documents first.")
    return sorted(({**item, "score": round(_cosine(vector, item["embedding"]), 4)}
                   for item in chunks), key=lambda item: item["score"], reverse=True)[:limit]


async def add_document(assignment_id: str, upload: UploadFile) -> dict:
    suffix = Path(upload.filename or "document").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(422, "Upload a PDF, PowerPoint, Markdown, or text file.")
    document_id = str(uuid4())
    safe_name = f"{document_id}{suffix}"
    path = UPLOAD_DIR / safe_name
    content = await upload.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Documents must be 10 MB or smaller.")
    stage = "storage"
    try:
        path.write_bytes(content)
        stage = "parsing"
        chunks = await run_in_threadpool(parse_resource, path)
        if not chunks:
            raise HTTPException(422, "No readable text was found in this document.")
        stage = "embedding"
        embeddings = await run_in_threadpool(embed_texts, [chunk.content for chunk in chunks])
        stage = "storage"
        _save_resource(document_id, assignment_id, upload.filename or safe_name,
                       upload.content_type or "application/octet-stream", path, chunks, embeddings)
    except Exception as exc:
        path.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, PowerPointConversionUnavailable):
            raise HTTPException(503, str(exc)) from exc
        if isinstance(exc, ResourceIngestionError):
            raise HTTPException(422, str(exc)) from exc
        logger.error("Document ingestion failed: stage=%s error_type=%s", stage, type(exc).__name__)
        if isinstance(exc, ImportError):
            if suffix in {".pptx", ".ppt"}:
                raise HTTPException(503, "PowerPoint processing dependencies are unavailable.") from exc
            raise HTTPException(503, "PDF processing dependencies are unavailable. Contact your instructor.") from exc
        if stage == "parsing":
            if suffix in {".pptx", ".ppt"}:
                raise HTTPException(422, "The presentation could not be processed. Upload a valid, unencrypted PPTX or PPT file.") from exc
            raise HTTPException(422, "The document could not be processed. Upload a readable, unencrypted PDF, text, or Markdown file.") from exc
        if stage == "embedding":
            raise HTTPException(502, "The document could not be indexed because embedding generation failed. Please retry.") from exc
        raise HTTPException(500, "The document could not be saved. Please retry.") from exc
    return {"id": document_id, "filename": upload.filename, "chunk_count": len(chunks)}


def _save_resource(document_id, assignment_id, filename, content_type, path, chunks, embeddings):
    """The existing atomic document/chunk insert, shared by uploads and URLs."""
    with connection() as conn:
        conn.execute(
            "INSERT INTO documents(id,assignment_id,filename,content_type,path,created_at) VALUES (?,?,?,?,?,?)",
            (document_id, assignment_id, filename, content_type, str(path), now()),
        )
        conn.executemany(
            "INSERT INTO chunks(id,document_id,position,content,embedding,metadata) VALUES (?,?,?,?,?,?)",
            [(str(uuid4()), document_id, chunk.position, chunk.content,
              json.dumps(vector), json.dumps(chunk.metadata))
             for chunk, vector in zip(chunks, embeddings, strict=True)],
        )


async def add_url_document(assignment_id: str, url: str) -> dict:
    document_id = str(uuid4())
    path = None
    stage = "download"
    try:
        content, content_type, final_url = await run_in_threadpool(fetch_resource_url, url)
        suffix = ".pdf" if content_type == "application/pdf" else ".html"
        path = UPLOAD_DIR / f"{document_id}{suffix}"
        stage = "storage"
        path.write_bytes(content)
        stage = "parsing"
        if suffix == ".pdf":
            # URL PDFs use exactly the upload PDF converter/chunker.
            chunks = await run_in_threadpool(ingest_resource, path)
            for chunk in chunks:
                chunk.metadata.update(source_url=url, final_url=final_url)
        else:
            chunks = await run_in_threadpool(ingest_html, path, url, final_url)
        if not chunks:
            raise ResourceIngestionError("No readable resource content was found.")
        parsed = urlsplit(final_url)
        filename = next((chunk.metadata["title"] for chunk in chunks if chunk.metadata.get("title")),
                        unquote(Path(parsed.path).name) or parsed.hostname)[:300]
        stage = "embedding"
        embeddings = await run_in_threadpool(embed_texts, [chunk.content for chunk in chunks])
        stage = "storage"
        _save_resource(document_id, assignment_id, filename, content_type, path, chunks, embeddings)
    except Exception as exc:
        if path is not None:
            path.unlink(missing_ok=True)
        if isinstance(exc, ResourceIngestionError):
            raise HTTPException(422, str(exc)) from exc
        if isinstance(exc, ImportError):
            raise HTTPException(503, "Resource processing dependencies are unavailable.") from exc
        logger.error("URL ingestion failed: stage=%s error_type=%s", stage, type(exc).__name__)
        if stage in {"download", "parsing"}:
            raise HTTPException(422, "The URL resource could not be read. Use a public HTML article or unencrypted PDF.") from exc
        if stage == "embedding":
            raise HTTPException(502, "The resource could not be indexed because embedding generation failed. Please retry.") from exc
        raise HTTPException(500, "The resource could not be saved. Please retry.") from exc
    return {"id": document_id, "filename": filename, "chunk_count": len(chunks)}


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
            """SELECT c.content,c.embedding,c.position,c.metadata,d.id AS document_id,d.filename
               FROM chunks c JOIN documents d ON d.id=c.document_id
               WHERE d.assignment_id=?""",
            (assignment_id,),
        ).fetchall()
    ranked = rank_chunks([{**dict(row), "embedding": json.loads(row["embedding"])} for row in rows], vector, limit)
    return [
        {"document_id": item["document_id"], "filename": item["filename"],
         "content": item["content"], "position": item["position"],
         "metadata": json.loads(item["metadata"]), "score": round(item["score"], 4)}
        for item in ranked
    ]
