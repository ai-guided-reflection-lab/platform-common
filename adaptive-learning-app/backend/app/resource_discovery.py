from __future__ import annotations

from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

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


class _ResultsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and "result__a" in values.get("class", ""):
            self._href = values.get("href")
            self._parts = []

    def handle_data(self, data):
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.results.append((" ".join(self._parts).strip(), self._href))
            self._href = None
            self._parts = []


def _normalize_result(title: str, href: str) -> dict | None:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(target)
        parsed = urlparse(href)
    provider = TRUSTED_DOMAINS.get(parsed.netloc.lower())
    if not provider and parsed.hostname and parsed.hostname.endswith(".edu"):
        provider = parsed.hostname
    if not provider or parsed.scheme != "https":
        return None
    path = parsed.path.lower()
    query_keys = {key.lower() for key in parse_qs(parsed.query)}
    if "/search" in path or query_keys.intersection({"q", "s", "query", "search"}):
        return None
    return {"title": title[:300] or provider, "url": href, "provider": provider}


def discover_resources(topic: str, limit: int = 3) -> list[dict]:
    normalized = _normalize_topic(topic)
    for key, resources in CURATED.items():
        if key in normalized or normalized in key:
            return resources[:limit]

    query = f'"{normalized}" tutorial guide (site:edu OR site:nasa.gov OR site:learn.microsoft.com OR site:developers.google.com OR site:ibm.com OR site:openstax.org)'
    found = []
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            response = client.get(
                f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                headers={"User-Agent": "Mozilla/5.0 AdaptiveLearning/1.0"},
            )
            response.raise_for_status()
        parser = _ResultsParser()
        parser.feed(response.text)
        seen = set()
        for title, href in parser.results:
            item = _normalize_result(title, href)
            if item and item["url"] not in seen:
                seen.add(item["url"])
                found.append(item)
            if len(found) >= limit:
                return found
    except httpx.HTTPError:
        pass

    # Do not disguise search pages or unrelated catalogs as topic-specific readings.
    return found[:limit]


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
