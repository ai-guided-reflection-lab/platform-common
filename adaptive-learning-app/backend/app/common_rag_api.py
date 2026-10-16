"""Service-authenticated access to SDL's common ingestion and retrieval pipeline."""
import os
import secrets
import httpx
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .config import OPENAI_EMBEDDING_MODEL
from .openai_client import embed_texts
from .rag import SUPPORTED_SUFFIXES, parse_resource, rank_chunks
from .resource_ingestion import ResourceIngestionError


def service_access(x_platform_service: str | None = Header(default=None)):
    expected = os.getenv("PLATFORM_SERVICE_TOKEN", "")
    if not expected or not x_platform_service or not secrets.compare_digest(expected, x_platform_service):
        raise HTTPException(401, "Valid platform service credentials are required.")


router = APIRouter(prefix="/internal/platform/rag", dependencies=[Depends(service_access)])


class EmbedInput(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=5000)
    dimensions: int = Field(ge=1, le=4096)
    model: str


def checked_embeddings(body: EmbedInput):
    if body.model != OPENAI_EMBEDDING_MODEL:
        raise HTTPException(409, "Configure ClubALL and SDL to use the same embedding model before indexing.")
    try:
        vectors = embed_texts(body.texts, dimensions=body.dimensions)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            detail = "The embedding provider rejected its configured API key. Ask an administrator to update OPENAI_API_KEY."
        elif exc.response.status_code == 429:
            detail = "The embedding provider quota or rate limit was reached. Retry after the provider limit is resolved."
        else:
            detail = "The embedding provider could not index this document. Please retry."
        raise HTTPException(503, detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, "The embedding provider could not be reached. Please retry.") from exc
    if len(vectors) != len(body.texts) or any(len(v) != body.dimensions for v in vectors):
        raise HTTPException(503, "SDL embeddings do not match the course index. Configure the embedding provider and dimensions; offline vectors cannot replace the course index.")
    return vectors


@router.post("/embeddings")
def embeddings(body: EmbedInput):
    return {"embeddings": checked_embeddings(body), "model": OPENAI_EMBEDDING_MODEL}


@router.post("/parse")
async def parse(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(422, "Upload PDF, PowerPoint, Word DOCX, Markdown, text, HTML, or LaTeX.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Documents must be 10 MB or smaller.")
    try:
        with TemporaryDirectory() as directory:
            path = Path(directory) / ("resource" + suffix)
            path.write_bytes(content)
            chunks = await run_in_threadpool(parse_resource, path)
        if not chunks:
            raise HTTPException(422, "No readable content was found in this document.")
        return {"chunks": [{"text": c.content, "position": c.position, "metadata": c.metadata,
                            "page_number": (c.metadata.get("page_numbers") or [None])[0]}
                           for c in chunks]}
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(503, "The document parser dependencies are unavailable.") from exc
    except ResourceIngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, "The document could not be parsed. Upload a readable, unencrypted file.") from exc


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    chunks: list[dict] = Field(max_length=10000)
    limit: int = Field(default=4, ge=1, le=20)
    dimensions: int = Field(ge=1, le=4096)
    model: str


@router.post("/search")
def search(body: SearchInput):
    if not body.chunks:
        return {"chunks": []}
    vector = checked_embeddings(EmbedInput(texts=[body.query], dimensions=body.dimensions, model=body.model))[0]
    try:
        selected = rank_chunks(body.chunks, vector, body.limit)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "Invalid indexed chunks.") from exc
    return {"chunks": [{k: v for k, v in c.items() if k != "embedding"} for c in selected]}
