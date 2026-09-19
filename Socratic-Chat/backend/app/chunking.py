from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ASSIGNMENT_PATTERN = re.compile(r"\bassignment\s+(\d+)\b", re.IGNORECASE)
CHUNKING_VERSION = "semantic-html-v2"


@dataclass(frozen=True)
class ChunkProfile:
    name: str
    target_tokens: int
    max_tokens: int
    overlap_tokens: int


@dataclass(frozen=True)
class SemanticChunk:
    text: str
    section_path: tuple[str, ...] = ()
    assignment_number: int | None = None
    token_count: int = 0
    profile: str = "default"


@dataclass(frozen=True)
class _Block:
    text: str
    section_path: tuple[str, ...] = ()
    assignment_number: int | None = None
    kind: str = "paragraph"


COURSE_CORE_PROFILE = ChunkProfile(
    name="course_core",
    target_tokens=300,
    max_tokens=500,
    overlap_tokens=40,
)

REFERENCE_BOOK_PROFILE = ChunkProfile(
    name="reference_book",
    target_tokens=650,
    max_tokens=900,
    overlap_tokens=100,
)

DEFAULT_PROFILE = ChunkProfile(
    name="default",
    target_tokens=450,
    max_tokens=700,
    overlap_tokens=80,
)


def approximate_token_count(text: str) -> int:
    """Estimate model tokens without coupling ingestion to a model tokenizer."""

    return len(TOKEN_PATTERN.findall(text))


def assignment_number_from_text(text: str) -> int | None:
    match = ASSIGNMENT_PATTERN.search(text)
    return int(match.group(1)) if match else None


def select_profile(title: str, text: str = "") -> ChunkProfile:
    marker = f"{title}\n{text[:1000]}".lower()
    if "software-engineering-3155-core" in marker or "software engineering 3155" in marker:
        return COURSE_CORE_PROFILE
    if "software engineering at google" in marker or re.search(r"(?:^|[/\\])ch\d{2}\.html?$", title.lower()):
        return REFERENCE_BOOK_PROFILE
    return DEFAULT_PROFILE


def _normalize(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def _normalize_code(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in value.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip()


class _StructuredHTMLParser(HTMLParser):
    _ignored_tags = {"head", "script", "style", "nav", "noscript", "svg", "template"}
    _block_tags = {"p", "li", "pre", "figcaption", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self._headings: list[str] = []
        self._assignment_number: int | None = None
        self._article_assignment_stack: list[int | None] = []
        self._ignored_depth = 0
        self._active_tag: str | None = None
        self._active_heading_level: int | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._ignored_tags:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return

        if tag == "article":
            self._article_assignment_stack.append(self._assignment_number)
            attributes = dict(attrs)
            article_id = attributes.get("id") or ""
            match = re.search(r"(?:^|[-_])assignment[-_](\d+)(?:$|[-_])", article_id, re.IGNORECASE)
            if match:
                self._assignment_number = int(match.group(1))
            return

        if re.fullmatch(r"h[1-6]", tag) and self._active_tag is None:
            self._active_tag = tag
            self._active_heading_level = int(tag[1])
            self._buffer = []
        elif tag in self._block_tags and self._active_tag is None:
            self._active_tag = tag
            self._buffer = []
        elif tag == "br" and self._active_tag:
            self._buffer.append("\n")
        elif tag in {"td", "th"} and self._active_tag == "tr" and self._buffer:
            self._buffer.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._ignored_tags:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth or tag != self._active_tag:
            if tag == "article" and self._article_assignment_stack:
                self._assignment_number = self._article_assignment_stack.pop()
            return

        text = _normalize_code("".join(self._buffer)) if self._active_tag == "pre" else _normalize("".join(self._buffer))
        if self._active_heading_level is not None:
            if text:
                level = self._active_heading_level
                self._headings = self._headings[: level - 1]
                while len(self._headings) < level - 1:
                    self._headings.append("")
                self._headings.append(text)
                heading_assignment = assignment_number_from_text(text)
                if level <= 2 and not self._article_assignment_stack:
                    self._assignment_number = heading_assignment
                elif heading_assignment is not None:
                    self._assignment_number = heading_assignment
        elif text:
            kind = "code" if tag == "pre" else ("list_item" if tag == "li" else tag)
            self.blocks.append(
                _Block(
                    text=text,
                    section_path=tuple(filter(None, self._headings)),
                    assignment_number=self._assignment_number,
                    kind=kind,
                )
            )

        self._active_tag = None
        self._active_heading_level = None
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._active_tag:
            self._buffer.append(data)


def html_blocks(html_text: str) -> list[_Block]:
    parser = _StructuredHTMLParser()
    parser.feed(html_text)
    parser.close()
    return parser.blocks


def text_blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    headings: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        value = _normalize(" ".join(pending))
        pending.clear()
        if value:
            heading_assignment = next(
                (number for heading in reversed(headings) if (number := assignment_number_from_text(heading)) is not None),
                None,
            )
            blocks.append(
                _Block(
                    text=value,
                    section_path=tuple(filter(None, headings)),
                    assignment_number=heading_assignment,
                )
            )

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        heading_match = MARKDOWN_HEADING_PATTERN.match(line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            heading = _normalize(heading_match.group(2))
            headings[:] = headings[: level - 1]
            while len(headings) < level - 1:
                headings.append("")
            headings.append(heading)
        elif not line:
            flush()
        elif re.match(r"^(?:[-*+] |\d+[.)] )", line):
            flush()
            heading_assignment = next(
                (number for heading in reversed(headings) if (number := assignment_number_from_text(heading)) is not None),
                None,
            )
            blocks.append(
                _Block(
                    text=_normalize(line),
                    section_path=tuple(filter(None, headings)),
                    assignment_number=heading_assignment,
                    kind="list_item",
                )
            )
        else:
            pending.append(line)
    flush()
    return blocks


def _split_long_text(text: str, max_tokens: int) -> list[str]:
    if approximate_token_count(text) <= max_tokens:
        return [text]

    sentences = SENTENCE_PATTERN.split(text)
    if len(sentences) == 1:
        words = text.split()
        return [" ".join(words[index : index + max_tokens]) for index in range(0, len(words), max_tokens)]

    parts: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if current and approximate_token_count(" ".join([*current, sentence])) > max_tokens:
            parts.append(" ".join(current))
            current = []
        if approximate_token_count(sentence) > max_tokens:
            parts.extend(_split_long_text(sentence, max_tokens))
        else:
            current.append(sentence)
    if current:
        parts.append(" ".join(current))
    return parts


def _expand_long_blocks(blocks: list[_Block], document_title: str, max_tokens: int) -> list[_Block]:
    expanded: list[_Block] = []
    for block in blocks:
        header_tokens = approximate_token_count(_context_header(document_title, block.section_path))
        body_limit = max(50, max_tokens - header_tokens)
        for part in _split_long_text(block.text, body_limit):
            expanded.append(
                _Block(
                    text=part,
                    section_path=block.section_path,
                    assignment_number=block.assignment_number,
                    kind=block.kind,
                )
            )
    return expanded


def _context_header(document_title: str, section_path: tuple[str, ...]) -> str:
    lines = [f"Document: {document_title}"]
    if section_path:
        lines.append(f"Section: {' > '.join(section_path)}")
    return "\n".join(lines)


def _trailing_overlap(blocks: list[_Block], overlap_tokens: int) -> list[_Block]:
    if overlap_tokens <= 0:
        return []
    selected: list[_Block] = []
    used = 0
    for block in reversed(blocks):
        size = approximate_token_count(block.text)
        if selected and used + size > overlap_tokens:
            break
        if size > overlap_tokens:
            break
        selected.append(block)
        used += size
    return list(reversed(selected))


def build_semantic_chunks(
    document_title: str,
    blocks: list[_Block],
    profile: ChunkProfile,
) -> list[SemanticChunk]:
    blocks = _expand_long_blocks(blocks, document_title, profile.max_tokens)
    chunks: list[SemanticChunk] = []
    current: list[_Block] = []
    current_path: tuple[str, ...] = ()
    current_assignment: int | None = None

    def emit() -> None:
        nonlocal current
        if not current:
            return
        body = "\n\n".join(block.text for block in current)
        header = _context_header(document_title, current_path)
        text = f"{header}\n\n{body}"
        chunks.append(
            SemanticChunk(
                text=text,
                section_path=current_path,
                assignment_number=current_assignment,
                token_count=approximate_token_count(text),
                profile=profile.name,
            )
        )

    for block in blocks:
        if current and (block.section_path != current_path or block.assignment_number != current_assignment):
            emit()
            current = []

        if not current:
            current_path = block.section_path
            current_assignment = block.assignment_number

        proposed = "\n\n".join(item.text for item in [*current, block])
        header_size = approximate_token_count(_context_header(document_title, current_path))
        would_exceed_max = current and approximate_token_count(proposed) + header_size > profile.max_tokens
        reached_target = current and approximate_token_count(" ".join(item.text for item in current)) >= profile.target_tokens

        if would_exceed_max or reached_target:
            previous = current
            emit()
            current = _trailing_overlap(previous, profile.overlap_tokens)
            current_path = block.section_path
            current_assignment = block.assignment_number
            overlap_and_block = "\n\n".join(item.text for item in [*current, block])
            if approximate_token_count(overlap_and_block) + header_size > profile.max_tokens:
                current = []
        current.append(block)

    emit()
    return chunks


def chunk_document(
    document_title: str,
    content: str,
    *,
    source_format: str | None = None,
    profile: ChunkProfile | None = None,
) -> list[SemanticChunk]:
    selected_profile = profile or select_profile(document_title, content)
    format_name = (source_format or "").lower().lstrip(".")
    is_html = format_name in {"html", "htm"} or bool(re.search(r"<html\b|<!doctype\s+html", content[:1000], re.IGNORECASE))
    blocks = html_blocks(content) if is_html else text_blocks(content)
    return build_semantic_chunks(document_title, blocks, selected_profile)
