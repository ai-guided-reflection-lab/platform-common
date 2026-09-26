from __future__ import annotations

import hashlib
import logging
import math
import re
from pathlib import Path
from time import monotonic
from typing import Any

from app import db, settings
from app.answer_evaluation import AnswerEvaluation, evaluation_tutor_instruction
from app.classifier import MessageClassification, is_contextual_meaning_request
from app.chunking import CHUNKING_VERSION, chunk_document
from app.pipeline_logging import (
    debug_digest,
    debug_preview,
    log_event,
    log_exception,
    publish_event,
    redacted_preview,
    trace_active,
    update_llm_request_snapshot,
    write_llm_request_snapshot,
)
from app.schemas import ChatMessage, Source
from app.socratic import (
    SocraticDecision,
    choose_socratic_strategy,
    socratic_system_instruction,
)


LOGGER = logging.getLogger(__name__)
WORD_PATTERN = re.compile(r"[a-zA-Z0-9']+")
PAGE_PATTERN = re.compile(r"\b(?:page|p\.?|pg\.?)\s*(\d{1,4})\b", re.IGNORECASE)
STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does",
    "for", "from", "had", "has", "have", "he", "her", "here", "his", "how", "i",
    "in", "is", "it", "its", "me", "my", "name", "of", "on", "or", "our", "she", "so",
    "tell", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to",
    "was", "we", "what", "when", "where", "which", "who", "why", "with", "you", "your",
}
RAG_DOCUMENT_SUFFIXES = {".txt", ".md", ".pdf", ".tex", ".html", ".htm"}


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


def requested_assignment_numbers(query: str) -> set[int]:
    requested: set[int] = set()
    for match in re.finditer(r"\bassignments?\s+(\d+)\s*(?:[-–—]|to)\s*(\d+)\b", query, re.IGNORECASE):
        start, end = int(match.group(1)), int(match.group(2))
        if 1 <= start <= end <= 100:
            requested.update(range(start, end + 1))
    for match in re.finditer(r"\bassignments?\s+(\d+)\b", query, re.IGNORECASE):
        requested.add(int(match.group(1)))
    return requested


def item_assignment_number(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") or {}
    value = metadata.get("assignment_number")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)

    structural_text = " ".join(
        [
            str(item.get("title", "")),
            " ".join(str(part) for part in metadata.get("section_path", [])),
            str(item.get("text", ""))[:300],
        ]
    )
    match = re.search(r"\bassignment\s+(\d+)\b|\bse3155-a(\d+)\b", structural_text, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def requested_page_number(query: str) -> int | None:
    match = PAGE_PATTERN.search(query)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def chunk_text(text: str) -> list[str]:
    # Compatibility wrapper for PDF pages and callers that expect plain strings;
    # the implementation now preserves paragraphs instead of slicing characters.
    return [chunk.text for chunk in chunk_document("Uploaded document", text)]


def is_relevant_search_result(item: dict[str, Any]) -> bool:
    """Require lexical evidence or sufficiently strong absolute semantic similarity."""
    try:
        dense_similarity = float(item.get("dense_similarity"))
    except (TypeError, ValueError):
        dense_similarity = float("-inf")
    try:
        sparse_score = float(item.get("sparse_score"))
    except (TypeError, ValueError):
        sparse_score = 0.0
    return (
        sparse_score >= settings.RAG_MIN_SPARSE_SCORE
        or dense_similarity >= settings.RAG_MIN_DENSE_SIMILARITY
    )


def document_id(
    title: str,
    text: str,
    conversation_id: str | None = None,
    course_id: str | None = None,
) -> str:
    scope = f"course:{course_id}" if course_id else (conversation_id or "global")
    digest = hashlib.sha256(f"{scope}\n{title}\n{text[:1200]}".encode("utf-8")).hexdigest()
    return digest[:16]


def create_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    config = settings.embedding_client_config()
    if config is None:
        raise RuntimeError("Configure a supported embedding provider to index and search documents.")

    from openai import OpenAI

    _provider, api_key, base_url, model = config
    client = OpenAI(api_key=api_key, base_url=base_url)
    vectors: list[list[float]] = []
    batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)
    for start in range(0, len(texts), batch_size):
        response = client.embeddings.create(
            model=model,
            input=texts[start : start + batch_size],
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        batch_vectors = [item.embedding for item in response.data]
        invalid_dimensions = [len(vector) for vector in batch_vectors if len(vector) != settings.EMBEDDING_DIMENSIONS]
        if invalid_dimensions:
            raise RuntimeError(
                f"Embedding model {model} returned {invalid_dimensions[0]} dimensions; "
                f"PostgreSQL expects {settings.EMBEDDING_DIMENSIONS}."
            )
        vectors.extend(batch_vectors)
    return vectors


def _semantic_chunk_rows(title: str, text: str) -> list[dict[str, object]]:
    suffix = Path(title).suffix.lower()
    return [
        {
            "text": chunk.text,
            "metadata": {
                "section_path": list(chunk.section_path),
                "chunk_profile": chunk.profile,
                "assignment_number": chunk.assignment_number,
                "approximate_token_count": chunk.token_count,
                "chunking_version": CHUNKING_VERSION,
            },
        }
        for chunk in chunk_document(title, text, source_format=suffix)
    ]


def ingest_text(
    title: str,
    text: str,
    conversation_id: str | None = None,
    course_id: str | None = None,
    file_id: str | None = None,
) -> tuple[str, int]:
    if not file_id:
        raise ValueError("A PostgreSQL rag_files file_id is required for ingestion.")
    doc_id = document_id(title, text, conversation_id, course_id)
    chunks = _semantic_chunk_rows(title, text)
    embeddings = create_embeddings([str(chunk["text"]) for chunk in chunks])
    added = db.replace_document_chunks(
        file_id, doc_id, title, chunks, embeddings, settings.embedding_model_name(),
        conversation_id=conversation_id, course_id=course_id,
    )
    return doc_id, added


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
    file_id: str | None = None,
) -> tuple[str, int]:
    if not file_id:
        raise ValueError("A PostgreSQL rag_files file_id is required for ingestion.")
    pages = read_pdf_pages(path)
    full_text = "\n".join(text for _, text in pages)
    doc_id = document_id(path.name, full_text, conversation_id, course_id)
    chunks: list[dict[str, object]] = []

    for page_number, page_text in pages:
        for chunk in chunk_text(page_text):
            chunks.append(
                {
                    "page_number": page_number,
                    "text": f"Page {page_number}: {chunk}",
                    "metadata": {"chunking_version": CHUNKING_VERSION},
                }
            )
    embeddings = create_embeddings([str(chunk["text"]) for chunk in chunks])
    added = db.replace_document_chunks(
        file_id, doc_id, path.name, chunks, embeddings, settings.embedding_model_name(),
        conversation_id=conversation_id, course_id=course_id,
    )
    return doc_id, added


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
    file_id: str | None = None,
) -> tuple[str, int]:
    if path.suffix.lower() == ".pdf":
        return ingest_pdf_file(path, conversation_id, course_id, file_id)
    text = read_document(path)
    return ingest_text(path.name, text, conversation_id, course_id, file_id)


def scan_raw_docs() -> tuple[int, int, list[str]]:
    settings.RAW_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    documents_scanned = 0
    chunks_added = 0
    skipped_files: list[str] = []
    ignore_path = settings.RAW_DOCS_DIR / ".ragignore"
    ignored_names = set()
    if ignore_path.exists():
        ignored_names = {
            line.strip()
            for line in ignore_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

    for path in settings.RAW_DOCS_DIR.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name in ignored_names:
            continue

        if path.suffix.lower() not in RAG_DOCUMENT_SUFFIXES:
            skipped_files.append(path.name)
            continue

        content = path.read_bytes()
        file_id = db.save_rag_file(path.name, "application/octet-stream", content)
        if not file_id:
            raise RuntimeError("PostgreSQL is required to scan RAG documents.")
        _, added = ingest_file(path, file_id=file_id)
        documents_scanned += 1
        chunks_added += added

    return documents_scanned, chunks_added, skipped_files


def retrieve(
    query: str,
    top_k: int = 4,
    conversation_id: str | None = None,
    course_id: str | None = None,
    subqueries: tuple[str, ...] = (),
) -> list[Source]:
    queries = [query]
    seen_queries = {query.casefold()}
    for candidate in subqueries[:3]:
        candidate = " ".join(candidate.split())
        if candidate and candidate.casefold() not in seen_queries:
            queries.append(candidate)
            seen_queries.add(candidate.casefold())
    log_event(5, "retrieval_started", retrieval_type="hybrid", top_k=top_k, query_count=len(queries))
    debug_digest("retrieval_query", query)
    for index, subquery in enumerate(queries[1:], start=1):
        debug_digest(f"retrieval_subquery_{index}", subquery)
    retrieval_started = monotonic()
    try:
        embedding_started = monotonic()
        query_embeddings = create_embeddings(queries)
        log_event(
            5,
            "query_embedding_completed",
            model=settings.embedding_model_name(),
            dimensions=len(query_embeddings[0]),
            query_count=len(queries),
            latency_ms=round((monotonic() - embedding_started) * 1000),
        )
        search_started = monotonic()
        ranked_by_query = [
            db.hybrid_search_chunks(
                search_query, query_embedding, top_k,
                conversation_id=conversation_id, course_id=course_id,
                assignment_numbers=requested_assignment_numbers(search_query),
            )
            for search_query, query_embedding in zip(queries, query_embeddings, strict=True)
        ]
        accepted_by_query = [
            [item for item in ranked if is_relevant_search_result(item)]
            for ranked in ranked_by_query
        ]
        # Take the strongest available result from each query in turn. This
        # preserves coverage of distinct question parts without repeating chunks.
        relevant: list[dict[str, Any]] = []
        seen_chunks: set[str] = set()
        coverage_order = accepted_by_query[1:] + accepted_by_query[:1] if len(queries) > 1 else accepted_by_query
        for rank in range(top_k):
            for accepted in coverage_order:
                if rank >= len(accepted):
                    continue
                item = accepted[rank]
                chunk_id = str(item["chunk_id"])
                if chunk_id not in seen_chunks:
                    relevant.append(item)
                    seen_chunks.add(chunk_id)
                if len(relevant) >= top_k:
                    break
            if len(relevant) >= top_k:
                break
        sources = [
            Source(
                document_id=item["document_id"],
                chunk_id=item["chunk_id"],
                title=f"{item['title']} p. {item['page_number']}" if item.get("page_number") else item["title"],
                text=item["text"],
                score=float(item["score"]),
                dense_similarity=float(item["dense_similarity"]),
                sparse_score=float(item["sparse_score"]),
            )
            for item in relevant
        ]
        log_event(
            5,
            "hybrid_search_completed",
            chunks=len(sources),
            candidates=sum(len(ranked) for ranked in ranked_by_query),
            relevant_candidates=sum(len(accepted) for accepted in accepted_by_query),
            rejected=sum(len(ranked) - len(accepted) for ranked, accepted in zip(ranked_by_query, accepted_by_query)),
            query_count=len(queries),
            min_dense_similarity=settings.RAG_MIN_DENSE_SIMILARITY,
            min_sparse_score=settings.RAG_MIN_SPARSE_SCORE,
            latency_ms=round((monotonic() - search_started) * 1000),
        )
        log_event(
            5,
            "retrieval_completed",
            retrieval_type="hybrid",
            chunks=len(sources),
            latency_ms=round((monotonic() - retrieval_started) * 1000),
        )
        for rank, source in enumerate(sources, start=1):
            debug_preview(
                "retrieved_chunk",
                source.text,
                max_chars=180,
                rank=rank,
                title=redacted_preview(source.title, max_chars=80),
                score=round(source.score, 6),
                dense_similarity=round(source.dense_similarity or 0.0, 6),
                sparse_score=round(source.sparse_score or 0.0, 6),
            )
        return sources
    except Exception as error:
        log_exception(5, "retrieval_failed", error, retrieval_type="hybrid")
        raise


def retrieve_by_titles(query: str, titles: list[str], top_k: int = 4) -> list[Source]:
    title_set = {title for title in titles if title}
    if not title_set:
        return []

    ranked = db.hybrid_search_chunks(
        query, create_embeddings([query])[0], top_k, titles=sorted(title_set),
    )
    relevant = [item for item in ranked if is_relevant_search_result(item)][:top_k]
    return [
        Source(
            document_id=item["document_id"],
            chunk_id=item["chunk_id"],
            title=f"{item['title']} p. {item['page_number']}" if item.get("page_number") else item["title"],
            text=item["text"],
            score=float(item["score"]),
            dense_similarity=float(item["dense_similarity"]),
            sparse_score=float(item["sparse_score"]),
        )
        for item in relevant
    ]


def retrieve_overview(
    conversation_id: str | None,
    top_k: int = 4,
    course_id: str | None = None,
) -> list[Source]:
    if not conversation_id and not course_id:
        return []
    log_event(5, "retrieval_started", retrieval_type="overview", top_k=top_k)
    retrieval_started = monotonic()
    try:
        matches = db.overview_chunks(conversation_id, course_id, top_k)
        sources = [
            Source(
                document_id=item["document_id"],
                chunk_id=item["chunk_id"],
                title=item["title"],
                text=item["text"],
                score=1.0,
            )
            for item in matches
        ]
        log_event(
            5,
            "retrieval_completed",
            retrieval_type="overview",
            chunks=len(sources),
            latency_ms=round((monotonic() - retrieval_started) * 1000),
        )
        for rank, source in enumerate(sources, start=1):
            debug_preview(
                "retrieved_chunk",
                source.text,
                max_chars=180,
                rank=rank,
                title=redacted_preview(source.title, max_chars=80),
                score=round(source.score, 6),
            )
        return sources
    except Exception as error:
        log_exception(5, "retrieval_failed", error, retrieval_type="overview")
        raise


def retrieve_snapshot(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 4,
) -> list[Source]:
    """Run hybrid retrieval against an assignment's immutable chunk snapshot."""
    if not chunks:
        return []
    log_event(5, "retrieval_started", retrieval_type="assignment_snapshot", top_k=top_k)
    query_embedding = create_embeddings([query])[0]
    query_tokens = set(tokenize(query))
    requested_assignments = requested_assignment_numbers(query)
    requested_page = requested_page_number(query)

    candidates = [
        chunk for chunk in chunks
        if (not requested_assignments or item_assignment_number(chunk) in requested_assignments)
        and (requested_page is None or chunk.get("page_number") == requested_page)
    ]
    if not candidates:
        candidates = chunks

    query_norm = math.sqrt(sum(value * value for value in query_embedding)) or 1.0
    scored: list[dict[str, Any]] = []
    for chunk in candidates:
        embedding = [float(value) for value in chunk.get("embedding", [])]
        embedding_norm = math.sqrt(sum(value * value for value in embedding)) or 1.0
        dense = (
            sum(left * right for left, right in zip(query_embedding, embedding))
            / (query_norm * embedding_norm)
            if embedding else 0.0
        )
        chunk_tokens = set(tokenize(str(chunk.get("text", ""))))
        sparse = len(query_tokens & chunk_tokens) / max(1, len(query_tokens))
        scored.append({**chunk, "dense_similarity": dense, "sparse_score": sparse})

    dense_rank = {
        item["chunk_id"]: rank
        for rank, item in enumerate(
            sorted(scored, key=lambda item: item["dense_similarity"], reverse=True), start=1,
        )
    }
    sparse_rank = {
        item["chunk_id"]: rank
        for rank, item in enumerate(
            sorted(
                (item for item in scored if item["sparse_score"] > 0),
                key=lambda item: item["sparse_score"], reverse=True,
            ),
            start=1,
        )
    }
    for item in scored:
        item["score"] = 1.0 / (60 + dense_rank[item["chunk_id"]])
        if item["chunk_id"] in sparse_rank:
            item["score"] += 1.0 / (60 + sparse_rank[item["chunk_id"]])

    relevant = [
        item for item in sorted(scored, key=lambda item: item["score"], reverse=True)
        if is_relevant_search_result(item)
    ][:top_k]
    sources = [
        Source(
            document_id=str(item["document_id"]),
            chunk_id=str(item["chunk_id"]),
            title=(
                f"{item['title']} p. {item['page_number']}"
                if item.get("page_number") else str(item["title"])
            ),
            text=str(item["text"]),
            score=float(item["score"]),
            dense_similarity=float(item["dense_similarity"]),
            sparse_score=float(item["sparse_score"]),
        )
        for item in relevant
    ]
    log_event(5, "retrieval_completed", retrieval_type="assignment_snapshot", chunks=len(sources))
    return sources


def snapshot_overview(chunks: list[dict[str, Any]], top_k: int = 4) -> list[Source]:
    """Return the first chunks from each snapshotted document for overview requests."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        document_id = str(chunk["document_id"])
        if document_id in seen:
            continue
        seen.add(document_id)
        selected.append(chunk)
        if len(selected) >= top_k:
            break
    return [
        Source(
            document_id=str(item["document_id"]),
            chunk_id=str(item["chunk_id"]),
            title=str(item["title"]),
            text=str(item["text"]),
            score=1.0,
        )
        for item in selected
    ]


def fallback_answer(question: str, sources: list[Source]) -> str:
    if not sources:
        return "That topic is outside the currently published course documentation."
    return (
        "I found relevant course material, but I could not generate the explanation right now. "
        "Please try again."
    )


_NON_REASONING_INVITATION = re.compile(
    r"^(?:(?:would|could|do)\s+you\s+(?:like|want|prefer)\b|"
    r"(?:are|were)\s+you\s+ready\b|"
    r"(?:shall|should)\s+we\b)",
    re.IGNORECASE,
)


def ensure_socratic_final_question(
    answer: str,
    decision: SocraticDecision,
) -> str:
    """Replace a closing activity offer with a question that requires reasoning."""
    if decision.mode != "socratic":
        return answer
    sentences = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", answer.strip())
        if sentence.strip()
    ]
    if not sentences:
        return answer
    final_question = sentences[-1].strip()
    plain_question = re.sub(r"[*_`]", "", final_question).strip()
    if not final_question.endswith("?") or not _NON_REASONING_INVITATION.match(plain_question):
        return answer
    concept = (decision.target_concept or "the main course concept").strip()
    if len(concept.split()) > 6:
        concept = "the main course concept"
    replacement = (
        f"What detail in this situation shows how {concept} works, "
        "and why does that detail matter?"
    )
    return " ".join([*sentences[:-1], replacement])


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


def generation_client_config() -> tuple[str, str, str, str] | None:
    """Use the configured OpenAI-compatible provider for tutor generation."""
    return settings.llm_client_config("generation")


async def generate_sample_student_answer(
    tutor_question: str,
    history: list[ChatMessage],
    sources: list[Source],
) -> str:
    """Draft a grounded student response without advancing the learning session."""
    client_config = generation_client_config()
    if client_config is None:
        raise RuntimeError("The generation model is not configured.")
    from openai import AsyncOpenAI

    provider, api_key, base_url, model = client_config
    context = "\n\n".join(f"[{index + 1}] {source.title}\n{source.text}" for index, source in enumerate(sources))
    messages = [
        {
            "role": "system",
            "content": (
                "Write a good example STUDENT answer to the tutor's latest question. "
                "Answer the question directly in first person as a student, using the current conversation's "
                "scenario, people, and terms. Build on the student's prior reasoning without merely repeating it. "
                "Use only facts supported by the instructor's retrieved material. "
                "Keep it to one or two clear sentences, preferably under 40 words. "
                "Do not ask a new question, add tutor feedback, or mention the documents. "
                "If the material does not support the question, say you cannot answer it from the course material."
            ),
        },
        {"role": "system", "content": f"Instructor material:\n{context}"},
        *[{"role": item.role, "content": item.content} for item in history[-8:]],
        {"role": "user", "content": f"Write the student's answer to this tutor question:\n{tutor_question}"},
    ]
    request: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2}
    if provider == "Ollama":
        request.update(settings.completion_token_parameters(provider, settings.OLLAMA_GENERATION_MAX_TOKENS))
    write_llm_request_snapshot("sample-student-answer", provider, request)
    started = monotonic()
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.chat.completions.create(**request)
    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        raise RuntimeError("The generation model returned an empty answer.")
    update_llm_request_snapshot(
        "sample-student-answer",
        raw_response=answer,
        final_response=answer,
        latency_ms=round((monotonic() - started) * 1000),
    )
    return answer


async def generate_answer(
    question: str,
    history: list[ChatMessage],
    sources: list[Source],
    classification: MessageClassification | None = None,
    evaluation: AnswerEvaluation | None = None,
    learning_topic: str | None = None,
) -> str:
    contextual_meaning = is_contextual_meaning_request(question, history)
    if not sources and not contextual_meaning:
        log_event(8, "generation_stopped", reason="no_relevant_context")
        answer = fallback_answer(question, sources)
        log_event(9, "candidate_response_generated", source="unsupported_topic_fallback", response_chars=len(answer))
        debug_preview("candidate_answer", answer)
        return answer
    client_config = generation_client_config()
    if client_config is None:
        log_event(8, "generation_fallback_selected", reason="provider_not_configured")
        answer = fallback_answer(question, sources)
        log_event(9, "candidate_response_generated", source="service_fallback", response_chars=len(answer))
        debug_preview("candidate_answer", answer)
        return answer
    from openai import AsyncOpenAI

    provider, api_key, base_url, model = client_config
    socratic_decision = choose_socratic_strategy(question, history, sources, classification, evaluation)
    log_event(
        6,
        "socratic_strategy_selected",
        learner_state=socratic_decision.student_state,
        strategy=socratic_decision.strategy,
        mode=socratic_decision.mode,
        scaffolding_level=socratic_decision.disclosure_level,
        input_question_type=classification.question_type if classification else "rules",
        target_concept=socratic_decision.target_concept or "unknown",
        example_type=socratic_decision.example_type,
        tutor_question_type=socratic_decision.tutor_question_type,
    )
    context = "\n\n".join(f"[{index + 1}] {source.title}\n{source.text}" for index, source in enumerate(sources))
    teaching_instruction = socratic_system_instruction(socratic_decision)
    if learning_topic:
        teaching_instruction += (
            f" The student's original learning question is <learning_topic>{learning_topic}</learning_topic>. "
            "That question is the primary teaching objective, not background context. Every Socratic follow-up "
            "must help the student reason about that objective. If the recent exchange has narrowed to a technical "
            "detail, briefly relate the detail to the original objective and ask about the original concept's "
            "purpose, decision, or review in the established scenario. Do not keep quizzing the student on the "
            "detail's inner workings. Do not invent new implementation details merely to extend the example. "
            "A different main learning goal requires a new chat."
        )
    if evaluation:
        teaching_instruction = f"{teaching_instruction} {evaluation_tutor_instruction(evaluation)}"
    recent_tutor_turns = [item for item in history[-8:] if item.role == "assistant" and "?" in item.content]
    if recent_tutor_turns and socratic_decision.mode == "socratic":
        teaching_instruction += (
            " The learner's latest message responds to a prior tutor question. Build on what they actually "
            "said; do not repeat or paraphrase a question they have already answered. If their answer is wrong, "
            "ask a smaller question about the specific mistaken assumption in the same scenario. "
            "Prior tutor questions are omitted from the dialogue below because they have already been answered. "
            "Do not reconstruct them from the learner's reply; move to the next consequence or decision."
        )
    generation_history = [
        {"role": item.role, "content": item.content}
        for item in history[-8:]
        if socratic_decision.mode == "direct" or item.role != "assistant" or "?" not in item.content
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "Explain wording from the previous tutor message using that message and its scenario. "
                "Resolve references from the conversation; do not invent course facts."
                if contextual_meaning else
                "You are a concise RAG tutor whose objective is student understanding of instructor-published topics. "
                "Write in a warm, natural conversational voice with complete sentences and smooth transitions. "
                "Avoid robotic phrasing, canned headings, telegraphic fragments, and disconnected short sentences. "
                "Use only the retrieved course context for factual course content. If that context does not support "
                "the requested topic, respond exactly: 'That topic is outside the currently published course "
                "documentation.' Never answer an unsupported topic from general knowledge, even if requested. "
                "Earlier tutor-generated examples are conversation context, not course evidence. Do not assert "
                "guarantees about identifiers or unseen state that the retrieved passage does not establish."
            ),
        },
        {"role": "system", "content": teaching_instruction},
        {"role": "system", "content": answer_format_instruction(question)},
        {"role": "system", "content": f"Retrieved context:\n{context or 'No context retrieved.'}"},
        *generation_history,
        {"role": "user", "content": question},
    ]
    prompt_chars = sum(len(str(message["content"])) for message in messages)
    log_event(7, "prompt_constructed", prompt_chars=prompt_chars, messages=len(messages))
    debug_digest("prompt", "\n".join(str(message["content"]) for message in messages))
    debug_preview("prompt_base_instruction", str(messages[0]["content"]))
    debug_preview("prompt_socratic_instruction", str(messages[1]["content"]))
    debug_preview("prompt_format_instruction", str(messages[2]["content"]))
    if settings.DEBUG_PIPELINE_LOGS:
        log_event(
            "debug",
            "prompt_inputs",
            history_roles=",".join(item["role"] for item in generation_history) or "none",
            history_messages=len(generation_history),
            retrieved_chunks=len(sources),
            question_chars=len(question),
        )

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        log_event(8, "llm_request_started", provider=provider, model=model)
        llm_started = monotonic()
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": settings.RAG_TEMPERATURE,
        }
        if provider == "Ollama":
            request.update(settings.completion_token_parameters(provider, settings.OLLAMA_GENERATION_MAX_TOKENS))
        write_llm_request_snapshot("tutor-generation", provider, request)
        response = await client.chat.completions.create(**request, stream=True)
        response_parts: list[str] = []
        if hasattr(response, "__aiter__"):
            async for chunk in response:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    response_parts.append(delta)
                    publish_event("llm_token", token=delta)
        else:
            content = response.choices[0].message.content if response.choices else None
            if content:
                response_parts.append(content)
        raw_answer = "".join(response_parts) or fallback_answer(question, sources)
        llm_latency_ms = round((monotonic() - llm_started) * 1000)
        log_event(
            8,
            "llm_request_completed",
            provider=provider,
            model=model,
            latency_ms=llm_latency_ms,
        )
        log_event(9, "candidate_response_generated", source="llm", response_chars=len(raw_answer))
        debug_preview("candidate_answer", raw_answer)
        answer = ensure_socratic_final_question(raw_answer, socratic_decision)
        log_event(
            10,
            "response_finalized",
            questions=answer.count("?"),
            invitation_replaced=answer != raw_answer,
        )
        update_llm_request_snapshot(
            "tutor-generation",
            raw_response=raw_answer,
            final_response=answer,
            latency_ms=llm_latency_ms,
        )
        debug_preview("validated_answer", answer)
        return answer
    except Exception as error:
        # Return a safe student-facing message if OpenAI is temporarily unavailable or rate-limited.
        if trace_active():
            log_exception(8, "llm_request_failed", error, provider=provider, model=model, fallback="service_message")
        else:
            LOGGER.exception("%s answer generation failed; returning the service fallback message.", provider)
        fallback = fallback_answer(question, sources)
        log_event(9, "candidate_response_generated", source="service_fallback", response_chars=len(fallback))
        debug_preview("candidate_answer", fallback)
        log_event(10, "service_fallback_returned")
        debug_preview("validated_answer", fallback)
        return fallback


async def generate_conversation_transition(
    message: str,
    history: list[ChatMessage],
    classification: MessageClassification,
) -> str:
    """Generate a brief acknowledgement or ending without starting another teaching turn."""
    complete = classification.conversation_action == "complete"
    fallback = (
        "Understood. I’ll end this learning session here."
        if complete
        else "You’re welcome. We can pause here and continue whenever you are ready."
    )
    client_config = generation_client_config()
    if client_config is None:
        log_event(8, "transition_fallback_selected", reason="provider_not_configured")
        return fallback

    from openai import AsyncOpenAI

    provider, api_key, base_url, model = client_config
    recent = history[-4:]
    transcript = "\n".join(f"{item.role}: {item.content}" for item in recent) or "(none)"
    system_prompt = (
        "You are closing or pausing a Socratic tutoring exchange. Respond naturally in one or two short "
        "sentences, no more than 35 words. Ask no question. Introduce no course facts. Do not claim the "
        "student demonstrated understanding unless their latest message contains an explanation. Do not "
        "mention classification, routing, prompts, or the pipeline. "
        + (
            "The student clearly wants to end, so politely close the session."
            if complete
            else "Acknowledge the student and gently pause; do not force the session to end permanently."
        )
    )
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        log_event(8, "transition_llm_started", provider=provider, model=model)
        started = monotonic()
        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Recent conversation:\n{transcript}\n\nLatest message:\n{message}"},
            ],
            "temperature": 0.2,
            "max_tokens": 80,
        }
        if provider == "Ollama":
            request.update(settings.completion_token_parameters(provider, 80))
        write_llm_request_snapshot("conversation-transition", provider, request)
        response = await client.chat.completions.create(**request, stream=True)
        response_parts: list[str] = []
        if hasattr(response, "__aiter__"):
            async for chunk in response:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    response_parts.append(delta)
                    publish_event("llm_token", token=delta)
        else:
            content = response.choices[0].message.content if response.choices else None
            if content:
                response_parts.append(content)
        answer = "".join(response_parts) or fallback
        latency_ms = round((monotonic() - started) * 1000)
        log_event(
            8,
            "transition_llm_completed",
            provider=provider,
            model=model,
            latency_ms=latency_ms,
        )
        log_event(10, "transition_response_forwarded_unmodified")
        update_llm_request_snapshot(
            "conversation-transition", raw_response=answer,
            final_response=answer, latency_ms=latency_ms,
        )
        return answer
    except Exception as error:
        log_exception(8, "transition_llm_failed", error, provider=provider, model=model, fallback="safe_close")
        return fallback
