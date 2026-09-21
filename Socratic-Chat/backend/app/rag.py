from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from time import monotonic
from typing import Any

from app import db, settings
from app.answer_evaluation import AnswerEvaluation, evaluation_tutor_instruction
from app.classifier import MessageClassification
from app.chunking import CHUNKING_VERSION, chunk_document
from app.pipeline_logging import (
    debug_digest,
    debug_preview,
    log_event,
    log_exception,
    redacted_preview,
    trace_active,
)
from app.schemas import ChatMessage, Source
from app.socratic import choose_socratic_strategy, enforce_socratic_response, socratic_system_instruction


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
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required to index and search documents.")

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_API_BASE_URL)
    vectors: list[list[float]] = []
    batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)
    for start in range(0, len(texts), batch_size):
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts[start : start + batch_size],
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        vectors.extend(item.embedding for item in response.data)
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
        file_id, doc_id, title, chunks, embeddings, settings.EMBEDDING_MODEL,
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
        file_id, doc_id, path.name, chunks, embeddings, settings.EMBEDDING_MODEL,
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
) -> list[Source]:
    log_event(5, "retrieval_started", retrieval_type="hybrid", top_k=top_k)
    debug_digest("retrieval_query", query)
    retrieval_started = monotonic()
    try:
        requested_assignments = requested_assignment_numbers(query)
        embedding_started = monotonic()
        query_embedding = create_embeddings([query])[0]
        log_event(
            5,
            "query_embedding_completed",
            model=settings.EMBEDDING_MODEL,
            dimensions=len(query_embedding),
            latency_ms=round((monotonic() - embedding_started) * 1000),
        )
        search_started = monotonic()
        ranked = db.hybrid_search_chunks(
            query, query_embedding, top_k, conversation_id=conversation_id,
            course_id=course_id, assignment_numbers=requested_assignments,
        )
        accepted = [item for item in ranked if is_relevant_search_result(item)]
        relevant = accepted[:top_k]
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
            candidates=len(ranked),
            relevant_candidates=len(accepted),
            rejected=len(ranked) - len(accepted),
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


def fallback_answer(question: str, sources: list[Source]) -> str:
    if not sources:
        return "That topic is outside the currently published course documentation."
    return (
        "I found relevant course material, but I could not generate the explanation right now. "
        "Please try again."
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


def generation_client_config() -> tuple[str, str, str, str] | None:
    """Use the configured OpenAI-compatible provider for tutor generation."""
    return settings.llm_client_config("generation")


async def generate_answer(
    question: str,
    history: list[ChatMessage],
    sources: list[Source],
    classification: MessageClassification | None = None,
    evaluation: AnswerEvaluation | None = None,
) -> str:
    if not sources:
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
        input_intent=classification.student_intent if classification else "rules",
        input_question_type=classification.question_type if classification else "rules",
        target_concept=socratic_decision.target_concept or "unknown",
        example_type=socratic_decision.example_type,
        tutor_question_type=socratic_decision.tutor_question_type,
    )
    context = "\n\n".join(f"[{index + 1}] {source.title}\n{source.text}" for index, source in enumerate(sources))
    teaching_instruction = socratic_system_instruction(socratic_decision)
    if evaluation:
        teaching_instruction = f"{teaching_instruction} {evaluation_tutor_instruction(evaluation)}"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a concise RAG tutor whose objective is student understanding of instructor-published topics. "
                "Use only the retrieved course context for factual course content. If that context does not support "
                "the requested topic, respond exactly: 'That topic is outside the currently published course "
                "documentation.' Never answer an unsupported topic from general knowledge, even if requested."
            ),
        },
        {"role": "system", "content": teaching_instruction},
        {"role": "system", "content": answer_format_instruction(question)},
        {"role": "system", "content": f"Retrieved context:\n{context or 'No context retrieved.'}"},
        *[{"role": item.role, "content": item.content} for item in history[-8:]],
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
            history_roles=",".join(item.role for item in history[-8:]) or "none",
            history_messages=len(history[-8:]),
            retrieved_chunks=len(sources),
            question_chars=len(question),
        )

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        log_event(8, "llm_request_started", provider=provider, model=model)
        llm_started = monotonic()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=settings.RAG_TEMPERATURE,
        )
        raw_answer = response.choices[0].message.content or fallback_answer(question, sources)
        log_event(
            8,
            "llm_request_completed",
            provider=provider,
            model=model,
            latency_ms=round((monotonic() - llm_started) * 1000),
        )
        log_event(9, "candidate_response_generated", source="llm", response_chars=len(raw_answer))
        debug_preview("candidate_answer", raw_answer)
        unsupported = raw_answer.strip().lower().startswith(
            "that topic is outside the currently published course documentation"
        ) or raw_answer.strip().lower().startswith("i do not know from your uploaded notes")
        answer = (
            "That topic is outside the currently published course documentation."
            if unsupported
            else enforce_socratic_response(raw_answer, question, socratic_decision)
        )
        changed = answer != raw_answer.strip()
        adjustment = "none"
        if changed:
            if socratic_decision.strategy == "diagnostic_recall":
                adjustment = "diagnostic_question_substituted"
            elif raw_answer.count("?") == 0:
                adjustment = "missing_question_repaired"
            elif raw_answer.count("?") > 1:
                adjustment = "multiple_questions_reduced"
            else:
                adjustment = "socratic_length_or_disclosure_policy"
        log_event(
            10,
            "response_validated",
            result="adjusted" if changed else "accepted",
            adjustment=adjustment,
            candidate_questions=raw_answer.count("?"),
            final_questions=answer.count("?"),
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
        log_event(10, "response_validated", result="accepted", adjustment="service_fallback")
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
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Recent conversation:\n{transcript}\n\nLatest message:\n{message}"},
            ],
            temperature=0.2,
            max_tokens=80,
        )
        answer = " ".join((response.choices[0].message.content or "").strip().split())
        log_event(
            8,
            "transition_llm_completed",
            provider=provider,
            model=model,
            latency_ms=round((monotonic() - started) * 1000),
        )
        if not answer or "?" in answer or len(answer.split()) > 35:
            log_event(10, "transition_response_rejected", reason="format_policy")
            return fallback
        log_event(10, "transition_response_validated", result="accepted")
        return answer
    except Exception as error:
        log_exception(8, "transition_llm_failed", error, provider=provider, model=model, fallback="safe_close")
        return fallback
