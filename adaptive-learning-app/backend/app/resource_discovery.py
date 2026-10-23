from __future__ import annotations

from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, wait
import logging
import os
import re
from time import monotonic
from urllib.parse import parse_qs, urlparse, urljoin

import httpx


TRUSTED_DOMAINS = {
    "www.geeksforgeeks.org": "GeeksforGeeks",
    "geeksforgeeks.org": "GeeksforGeeks",
    "www.tutorialspoint.com": "TutorialsPoint",
    "tutorialspoint.com": "TutorialsPoint",
    "www.ibm.com": "IBM",
    "ibm.com": "IBM",
    "learn.microsoft.com": "Microsoft Learn",
    "developers.google.com": "Google for Developers",
    "aws.amazon.com": "AWS",
    "docs.aws.amazon.com": "AWS",
    "huggingface.co": "Hugging Face",
    "openstax.org": "OpenStax",
    "www.open.edu": "Open University",
    "open.edu": "Open University",
    "ocw.mit.edu": "MIT OpenCourseWare",
    "developer.mozilla.org": "MDN",
    "en.wikipedia.org": "Wikipedia",
    "www.nasa.gov": "NASA",
    "www.sei.cmu.edu": "Carnegie Mellon Software Engineering Institute",
}

CURATED = {
    "operating system processes": [
        {"title": "Operating Systems: Processes", "url": "https://www.cs.uic.edu/~jbell/CourseNotes/OperatingSystems/3_Processes.html", "provider": "University of Illinois Chicago"},
        {"title": "OSTEP: The Abstraction — The Process", "url": "https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-intro.pdf", "provider": "University of Wisconsin–Madison"},
        {"title": "Operating System Processes", "url": "https://cs.pomona.edu/classes/cs105/archive/2022fa/lectures/08-Processes/Processes.pdf", "provider": "Pomona College"},
    ],
    "requirements": [
        {"title": "How to Write a Good Requirement", "url": "https://www.nasa.gov/reference/appendix-c-how-to-write-a-good-requirement/", "provider": "NASA"},
        {"title": "Software Requirements", "url": "https://www.sei.cmu.edu/library/software-requirements/", "provider": "Carnegie Mellon Software Engineering Institute"},
        {"title": "System Design Processes", "url": "https://www.nasa.gov/reference/4-0-system-design-processes/", "provider": "NASA"},
    ],
    "large language model": [
        {
            "title": "Introduction to Large Language Models",
            "url": "https://developers.google.com/machine-learning/crash-course/llm",
            "provider": "Google for Developers",
        },
        {
            "title": "What are large language models?",
            "url": "https://www.ibm.com/think/topics/large-language-models",
            "provider": "IBM",
        },
        {
            "title": "What is a Large Language Model?",
            "url": "https://aws.amazon.com/what-is/large-language-model/",
            "provider": "AWS",
        },
    ],
    "system architecture": [
        {
            "title": "Computer Systems Organization",
            "url": "https://openstax.org/books/introduction-computer-science/pages/5-1-computer-systems-organization",
            "provider": "OpenStax",
        },
        {
            "title": "Components of an IT System",
            "url": "https://www.open.edu/openlearn/mod/oucontent/view.php?id=47638&section=2.2",
            "provider": "Open University",
        },
        {
            "title": "Architecture Styles and Their Trade-offs",
            "url": "https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/",
            "provider": "Microsoft Learn",
        },
    ],
    "software architecture": [
        {
            "title": "Architecture Styles and Their Trade-offs",
            "url": "https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/",
            "provider": "Microsoft Learn",
        },
        {
            "title": "Application Architecture Fundamentals",
            "url": "https://learn.microsoft.com/en-us/azure/architecture/guide/",
            "provider": "Microsoft Learn",
        },
        {
            "title": "Application Architecture Types",
            "url": "https://www.ibm.com/think/topics/application-architecture-types",
            "provider": "IBM",
        },
    ],
}


def _normalize_topic(topic: str) -> str:
    normalized = " ".join(topic.lower().split())
    common_typos = {
        "arhcitecture": "architecture",
        "architechture": "architecture",
        "langauge": "language",
    }
    for typo, correction in common_typos.items():
        normalized = normalized.replace(typo, correction)
    return normalized


logger = logging.getLogger(__name__)
READING_BUDGET_SECONDS = 10
DEFAULT_READING_DOMAINS = "learn.microsoft.com,aws.amazon.com,docs.aws.amazon.com,www.ibm.com,ibm.com,developer.mozilla.org,ocw.mit.edu,www.nasa.gov,www.sei.cmu.edu,openstax.org,www.open.edu,open.edu,www.cs.uic.edu,pages.cs.wisc.edu,cs.pomona.edu,developers.google.com"


def _allowed_domains():
    return {host.strip().lower() for host in os.getenv("SDL_READING_DOMAINS", DEFAULT_READING_DOMAINS).split(",") if host.strip()}


def _normalize_result(title: str, href: str) -> dict | None:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    try:
        if parsed.scheme != "https" or host not in _allowed_domains() or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
    except ValueError:
        return None
    provider = TRUSTED_DOMAINS.get(host, host)
    path = parsed.path.lower()
    query_keys = {key.lower() for key in parse_qs(parsed.query)}
    if "/search" in path or query_keys.intersection({"q", "s", "query", "search"}):
        return None
    return {"title": title[:300] or provider, "url": href, "provider": provider}


def discover_resources(topic: str, limit: int = 3) -> list[dict]:
    """Use a small curated catalog only; never query a general web search engine."""
    normalized = _normalize_topic(topic)
    def terms(text):
        return {word[:-2] if word.endswith("sses") else word[:-1] if word.endswith("s") and not word.endswith("ss") else word for word in re.findall(r"[a-z0-9]+", text)}
    words = terms(normalized)
    if {"software", "design"}.issubset(words):
        normalized += " software architecture"
    for key, resources in CURATED.items():
        if key in normalized or normalized in key or terms(key).issubset(terms(normalized)):
            return [item for resource in resources if (item := _normalize_result(resource["title"], resource["url"]))][:min(limit, 3)]
    return []


class _ReadingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer", "header"}:
            self.ignored += 1
        if tag in {"p", "li"}:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "header"}:
            self.ignored = max(0, self.ignored - 1)
        if tag in {"p", "li"}:
            self.depth = max(0, self.depth - 1)

    def handle_data(self, text):
        if self.depth and not self.ignored and text.strip():
            self.parts.append(text.strip())


def verify_resources(candidates: list[dict], topic: str, limit: int = 3) -> list[dict]:
    """Check at most three curated links within one ten-second wall-clock budget."""
    deadline = monotonic() + READING_BUDGET_SECONDS
    selected = []
    seen = set()
    for candidate in candidates:
        item = _normalize_result(str(candidate.get("title", "")), str(candidate.get("url", "")))
        if item and item["url"] not in seen:
            selected.append(item)
            seen.add(item["url"])
        if len(selected) == min(max(limit, 0), 3):
            break
    if not selected or limit <= 0:
        return []

    def check(item):
        current = item["url"]
        try:
            with httpx.Client(timeout=2.5, follow_redirects=False) as client:
                for _ in range(3):
                    if deadline <= monotonic():
                        return None
                    with client.stream("GET", current, timeout=min(2.5, deadline - monotonic())) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            target = urljoin(current, response.headers.get("location", ""))
                            if not _normalize_result(item["title"], target):
                                logger.info("Supplemental reading skipped: host=%s reason=unapproved_redirect", urlparse(current).hostname)
                                return None
                            current = target
                            continue
                        response.raise_for_status()
                        if not any(kind in response.headers.get("content-type", "").lower() for kind in ("text/html", "application/pdf")):
                            logger.info("Supplemental reading skipped: host=%s reason=content_type", urlparse(current).hostname)
                            return None
                    return {**item, "url": current, "provider": TRUSTED_DOMAINS.get(urlparse(current).hostname, urlparse(current).hostname),
                            "description": f"Optional educational reading about {topic}.",
                            "focus": f"Relate this reading to the explanations and examples in the uploaded course material."}
        except httpx.HTTPError as exc:
            logger.info("Supplemental reading skipped: host=%s reason=%s", urlparse(current).hostname, type(exc).__name__)
        return None

    pool = ThreadPoolExecutor(max_workers=3)
    tasks = [pool.submit(check, item) for item in selected]
    try:
        done, pending = wait(tasks, timeout=max(0, deadline - monotonic()))
        if pending:
            logger.info("Supplemental reading budget reached; continuing with uploaded course material")
        return [result for task in tasks if task in done and (result := task.result())]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def read_resource_excerpts(resources: list[dict]) -> list[dict]:
    """Fetch bounded excerpts from trusted publishers for grounded examples."""
    def read(resource):
        if not _normalize_result(resource["title"], resource["url"]):
            return None
        try:
            # Do not follow redirects to unvalidated destinations.
            with httpx.Client(timeout=8, follow_redirects=False) as client:
                with client.stream("GET", resource["url"]) as response:
                    response.raise_for_status()
                    if "text/html" not in response.headers.get("content-type", ""):
                        return None
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) >= 250_000:
                            break
            parser = _ReadingParser()
            parser.feed(content.decode("utf-8", errors="replace"))
            excerpt = " ".join(parser.parts)[:6000]
            return {**resource, "excerpt": excerpt} if excerpt else None
        except httpx.HTTPError:
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        return [item for item in pool.map(read, resources[:3]) if item]
