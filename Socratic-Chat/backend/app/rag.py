from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app import settings
from app.schemas import ChatMessage, Source


WORD_PATTERN = re.compile(r"[a-zA-Z0-9']+")
PAGE_PATTERN = re.compile(r"\b(?:page|p\.?|pg\.?)\s*(\d{1,4})\b", re.IGNORECASE)
STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does",
    "for", "from", "had", "has", "have", "he", "her", "here", "his", "how", "i",
    "in", "is", "it", "its", "me", "my", "name", "of", "on", "or", "our", "she", "so",
    "tell", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to",
    "was", "we", "what", "when", "where", "which", "who", "why", "with", "you", "your",
}
RAG_DOCUMENT_SUFFIXES = {".txt", ".md", ".pdf", ".tex"}
MIN_RELEVANCE_SCORE = 0.12
MIN_SHARED_TERMS = 2


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in (match.group(0).lower() for match in WORD_PATTERN.finditer(text))
        if (len(token) > 2 or token.isdigit()) and token not in STOP_WORDS
    ]


def requested_numbered_item(query: str) -> str | None:
    match = re.search(r"\b(?:assignment|project(?:\s+part)?)\s+\d+\b", query, re.IGNORECASE)
    if not match:
        return None
    return " ".join(match.group(0).lower().split())


def requested_page_number(query: str) -> int | None:
    match = PAGE_PATTERN.search(query)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def chunk_text(text: str, chunk_size: int = 850, overlap: int = 140) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        if end < len(clean):
            boundary = max(clean.rfind(".", start, end), clean.rfind("?", start, end), clean.rfind("!", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunks.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def document_id(
    title: str,
    text: str,
    conversation_id: str | None = None,
    course_id: str | None = None,
) -> str:
    scope = f"course:{course_id}" if course_id else (conversation_id or "global")
    digest = hashlib.sha256(f"{scope}\n{title}\n{text[:1200]}".encode("utf-8")).hexdigest()
    return digest[:16]


def load_index() -> list[dict[str, Any]]:
    if not settings.INDEX_PATH.exists():
        return []
    try:
        data = json.loads(settings.INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_index(items: list[dict[str, Any]]) -> None:
    settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    settings.INDEX_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def ingest_text(
    title: str,
    text: str,
    conversation_id: str | None = None,
    course_id: str | None = None,
) -> tuple[str, int]:
    doc_id = document_id(title, text, conversation_id, course_id)
    existing = load_index()
    existing_ids = {item["chunk_id"] for item in existing}
    new_items = []

    for index, chunk in enumerate(chunk_text(text)):
        chunk_id = f"{doc_id}:{index}"
        if chunk_id in existing_ids:
            continue
        new_items.append(
            {
                "document_id": doc_id,
                "chunk_id": chunk_id,
                "conversation_id": conversation_id,
                "course_id": course_id,
                "title": title,
                "text": chunk,
                "tokens": tokenize(chunk),
            }
        )

    if conversation_id:
        for item in existing:
            if item.get("chunk_id", "").startswith(f"{doc_id}:") and not item.get("conversation_id"):
                item["conversation_id"] = conversation_id

    save_index([*existing, *new_items])
    return doc_id, len(new_items)


def read_pdf_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from PyPDF2 import PdfReader
    except ModuleNotFoundError as exc:
        raise RuntimeError("PDF support needs PyPDF2. Run: python -m pip install PyPDF2") from exc

    reader = PdfReader(str(path))
    return [
        (page_number, page.extract_text() or "")
        for page_number, page in enumerate(reader.pages, start=1)
    ]


def ingest_pdf_file(
    path: Path,
    conversation_id: str | None = None,
    course_id: str | None = None,
) -> tuple[str, int]:
    pages = read_pdf_pages(path)
    full_text = "\n".join(text for _, text in pages)
    doc_id = document_id(path.name, full_text, conversation_id, course_id)
    existing = load_index()
    existing_ids = {item["chunk_id"] for item in existing}
    new_items = []

    for page_number, page_text in pages:
        for chunk_index, chunk in enumerate(chunk_text(page_text)):
            chunk_id = f"{doc_id}:p{page_number}:{chunk_index}"
            if chunk_id in existing_ids:
                continue
            new_items.append(
                {
                    "document_id": doc_id,
                    "chunk_id": chunk_id,
                    "conversation_id": conversation_id,
                    "course_id": course_id,
                    "page_number": page_number,
                    "title": path.name,
                    "text": f"Page {page_number}: {chunk}",
                    "tokens": tokenize(chunk),
                }
            )

    save_index([*existing, *new_items])
    return doc_id, len(new_items)


def read_latex_document(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)
    text = re.sub(
        r"\\(?:documentclass|usepackage|includegraphics|bibliography|bibliographystyle)"
        r"\*?(?:\[[^\]]*\])?\{[^{}]*\}",
        " ",
        text,
    )
    text = re.sub(
        r"\\(?:cite|citep|citet|ref|eqref|label|url|href)"
        r"\*?(?:\[[^\]]*\])?\{[^{}]*\}(?:\{([^{}]*)\})?",
        lambda match: f" {match.group(1) or ''} ",
        text,
    )
    text = re.sub(
        r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph|title|author|caption)"
        r"\*?\{([^{}]*)\}",
        r"\n\1\n",
        text,
    )
    text = re.sub(r"\\(?:begin|end)\{[^{}]*\}", "\n", text)
    text = re.sub(r"\\item(?:\[[^\]]*\])?", "\n- ", text)
    text = re.sub(r"\\([%&#_$])", r"\1", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("\\\\", "\n")
    text = re.sub(r"[{}$]", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join(text for _, text in read_pdf_pages(path))
    if path.suffix.lower() == ".tex":
        return read_latex_document(path)

    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_file(
    path: Path,
    conversation_id: str | None = None,
    course_id: str | None = None,
) -> tuple[str, int]:
    if path.suffix.lower() == ".pdf":
        return ingest_pdf_file(path, conversation_id, course_id)
    text = read_document(path)
    return ingest_text(path.name, text, conversation_id, course_id)


def scan_raw_docs() -> tuple[int, int, list[str]]:
    settings.RAW_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    documents_scanned = 0
    chunks_added = 0
    skipped_files: list[str] = []

    for path in settings.RAW_DOCS_DIR.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue

        if path.suffix.lower() not in RAG_DOCUMENT_SUFFIXES:
            skipped_files.append(path.name)
            continue

        _, added = ingest_file(path)
        documents_scanned += 1
        chunks_added += added

    return documents_scanned, chunks_added, skipped_files


def score(query_tokens: list[str], chunk_tokens: list[str]) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0

    query_counts = Counter(query_tokens)
    chunk_counts = Counter(chunk_tokens)
    shared = set(query_counts) & set(chunk_counts)
    if len(shared) < min(MIN_SHARED_TERMS, len(set(query_tokens))):
        return 0.0

    numerator = sum(query_counts[token] * chunk_counts[token] for token in shared)
    query_norm = math.sqrt(sum(value * value for value in query_counts.values()))
    chunk_norm = math.sqrt(sum(value * value for value in chunk_counts.values()))
    if query_norm == 0 or chunk_norm == 0:
        return 0.0
    return numerator / (query_norm * chunk_norm)


def retrieve(
    query: str,
    top_k: int = 4,
    conversation_id: str | None = None,
    course_id: str | None = None,
) -> list[Source]:
    query_tokens = tokenize(query)
    requested_page = requested_page_number(query)
    numbered_item = requested_numbered_item(query)
    ranked = []
    page_ranked = []

    for item in load_index():
        if course_id and item.get("course_id") != course_id:
            continue
        if not course_id and conversation_id and item.get("conversation_id") != conversation_id:
            continue

        item_score = score(query_tokens, item.get("tokens", []))
        if numbered_item:
            normalized_item_text = " ".join(str(item.get("text", "")).lower().split())
            if re.search(rf"\b{re.escape(numbered_item)}\b", normalized_item_text):
                item_score = max(item_score, 1.0)
        if item_score < MIN_RELEVANCE_SCORE:
            continue

        if requested_page and item.get("page_number") == requested_page:
            page_ranked.append((item_score + 1.0, item))
        elif not requested_page:
            ranked.append((item_score, item))

    ranked = page_ranked or ranked
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [
        Source(
            document_id=item["document_id"],
            chunk_id=item["chunk_id"],
            title=f"{item['title']} p. {item['page_number']}" if item.get("page_number") else item["title"],
            text=item["text"],
            score=float(item_score),
        )
        for item_score, item in ranked[:top_k]
    ]


def retrieve_by_titles(query: str, titles: list[str], top_k: int = 4) -> list[Source]:
    title_set = {title for title in titles if title}
    if not title_set:
        return []

    query_tokens = tokenize(query)
    ranked = []

    for item in load_index():
        if item.get("title") not in title_set:
            continue

        item_score = score(query_tokens, item.get("tokens", []))

        # Short concept questions like "what is regression?" can produce a
        # score below the normal threshold because there is only one useful
        # query token. Keep exact term hits as a low-confidence fallback.
        if item_score < MIN_RELEVANCE_SCORE:
            shared = set(query_tokens) & set(item.get("tokens", []))
            if not shared:
                continue
            item_score = 0.13

        ranked.append((item_score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [
        Source(
            document_id=item["document_id"],
            chunk_id=item["chunk_id"],
            title=f"{item['title']} p. {item['page_number']}" if item.get("page_number") else item["title"],
            text=item["text"],
            score=float(item_score),
        )
        for item_score, item in ranked[:top_k]
    ]


def retrieve_overview(
    conversation_id: str | None,
    top_k: int = 4,
    course_id: str | None = None,
) -> list[Source]:
    if not conversation_id and not course_id:
        return []

    matches = [
        item
        for item in load_index()
        if (
            (course_id and item.get("course_id") == course_id)
            or (not course_id and item.get("conversation_id") == conversation_id)
        )
    ]

    return [
        Source(
            document_id=item["document_id"],
            chunk_id=item["chunk_id"],
            title=item["title"],
            text=item["text"],
            score=1.0,
        )
        for item in matches[:top_k]
    ]


def delete_document(document_id: str, course_id: str | None = None) -> int:
    items = load_index()
    remaining = [
        item
        for item in items
        if not (
            item.get("document_id") == document_id
            and (course_id is None or item.get("course_id") == course_id)
        )
    ]
    removed = len(items) - len(remaining)
    if removed:
        save_index(remaining)
    return removed


def course_document_ids(course_id: str) -> set[str]:
    return {
        str(item["document_id"])
        for item in load_index()
        if item.get("course_id") == course_id and item.get("document_id")
    }


def fallback_answer(question: str, sources: list[Source]) -> str:
    if not sources:
        return (
            "I do not know from your uploaded notes. "
            "I could not find relevant context in the indexed documents."
        )

    source_notes = "\n\n".join(f"- {source.text}" for source in sources[:3])
    return (
        "Here is what I found in your notes:\n\n"
        f"{source_notes}\n\n"
        "To go deeper, ask: which sentence in the source best supports this answer?"
    )


def answer_format_instruction(question: str) -> str:
    query_tokens = set(tokenize(question))
    if "assignment" in query_tokens:
        return (
            "Format an assignment answer as one compact Markdown table with columns 'Field' and 'Details'. "
            "Use rows such as Assignment, Objective, Requirements, Submission, Points, and Due date, but include "
            "only rows supported by the retrieved context. Use plain text inside cells, concise phrases, and no "
            "paragraph before the table."
        )
    if "project" in query_tokens:
        return (
            "Format project information as a compact Markdown table. Use plain text inside cells, distinguish project "
            "parts when present, and include only facts supported by the retrieved context."
        )
    return "Prefer short paragraphs and bullets when they improve readability."


async def generate_answer(question: str, history: list[ChatMessage], sources: list[Source]) -> str:
    if not settings.OPENAI_API_KEY:
        return fallback_answer(question, sources)

    from openai import AsyncOpenAI

    context = "\n\n".join(f"[{index + 1}] {source.title}\n{source.text}" for index, source in enumerate(sources))
    messages = [
        {
            "role": "system",
            "content": (
                "You are a concise RAG tutor. Use the retrieved context first. "
                "If the context does not contain the answer, say: "
                "'I do not know from your uploaded notes.' Do not answer from general knowledge unless the user asks for that."
            ),
        },
        {"role": "system", "content": answer_format_instruction(question)},
        {"role": "system", "content": f"Retrieved context:\n{context or 'No context retrieved.'}"},
        *[{"role": item.role, "content": item.content} for item in history[-8:]],
        {"role": "user", "content": question},
    ]

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=settings.RAG_MODEL,
        messages=messages,
        temperature=settings.RAG_TEMPERATURE,
    )
    return response.choices[0].message.content or ""
