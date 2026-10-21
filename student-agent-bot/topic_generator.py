"""Auto-generate a topic draft from name + Firecrawl + LLM."""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from firecrawl import FirecrawlApp, ScrapeOptions
from langchain_core.messages import HumanMessage, SystemMessage

from models import PROVIDERS, get_model, invoke_with_retry
from topic_store import _slugify, validate_topic

# Prefer beginner tutorials. w3schools.in /software-engineering/ paths often 404,
# so TutorialsPoint / Javatpoint are real fallbacks — never a search-page URL.
READING_SITES = (
    "w3schools.in",
    "w3schools.com",
    "geeksforgeeks.org",
    "tutorialspoint.com",
    "javatpoint.com",
)

_SKIP_URL_SNIPPETS = (
    "/search",
    "/tag/",
    "/tags/",
    "/category/",
    "/author/",
    "/login",
    "/signup",
    "/premium",
    "/courses/",
    "/practice",
    "/quiz",
    "/user/",
    "/forums",
    "/jobs",
)


def pick_provider(preferred: str | None = None) -> str:
    if preferred and preferred in PROVIDERS and os.getenv(PROVIDERS[preferred]["env_key"]):
        return preferred
    for key in ("groq", "openai"):
        if os.getenv(PROVIDERS[key]["env_key"]):
            return key
    raise RuntimeError("Set GROQ_API_KEY or OPENAI_API_KEY in env")


def _result_field(result, key: str, default=""):
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _looks_like_article(url: str, site: str) -> bool:
    if not url or site not in url.lower():
        return False
    lower = url.lower()
    if any(snippet in lower for snippet in _SKIP_URL_SNIPPETS):
        return False
    path = urlparse(url).path.rstrip("/")
    segments = [part for part in path.split("/") if part]
    return len(segments) >= 1


def _clean_excerpt(markdown: str) -> str:
    markdown = re.sub(r"\s+", " ", markdown or "").strip()
    return markdown[:2500]


def _title_overlap(title: str, topic_name: str) -> int:
    title_words = set(re.findall(r"[a-z0-9]+", title.lower()))
    topic_words = set(re.findall(r"[a-z0-9]+", topic_name.lower()))
    return len(title_words & topic_words)


def _search_site(topic_name: str, site: str) -> dict | None:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY not set in env file")

    app = FirecrawlApp(api_key=api_key)
    queries = [
        f"{topic_name} site:{site}",
        f"{topic_name} software engineering site:{site}",
    ]

    candidates: list[dict] = []
    for query in queries:
        response = app.search(
            query=query,
            limit=5,
            scrape_options=ScrapeOptions(formats=["markdown"]),
        )
        if hasattr(response, "success") and not response.success:
            continue

        data = response.data if hasattr(response, "data") else response
        if not data:
            continue

        for result in data:
            url = _result_field(result, "url")
            if not _looks_like_article(url, site):
                continue
            excerpt = _clean_excerpt(_result_field(result, "markdown") or "")
            title = _result_field(result, "title") or f"{topic_name} — {site}"
            blob = f"{title} {excerpt}".lower()
            if len(excerpt) < 120 or re.search(r"\b404\b|page not found|page doesn.?t exist", blob):
                continue
            candidates.append({"title": title, "url": url, "excerpt": excerpt})

        if candidates:
            break

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            _title_overlap(item["title"], topic_name),
            len(item["excerpt"]),
        ),
        reverse=True,
    )
    return candidates[0]


def _find_two_resources(name: str) -> tuple[dict, dict]:
    found: list[dict] = []
    seen_urls: set[str] = set()

    for site in READING_SITES:
        hit = _search_site(name, site)
        if not hit:
            continue
        url = hit["url"].rstrip("/")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        found.append(hit)
        if len(found) >= 2:
            break

    if not found:
        raise RuntimeError(
            f"Could not find beginner articles for '{name}'. "
            "Try a more specific topic name."
        )
    if len(found) < 2:
        raise RuntimeError(
            f"Found only one working article for '{name}'. "
            "Try a more specific name, or paste a second URL by hand after generating."
        )

    return found[0], found[1]


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _llm_fill_topic(
    name: str,
    provider: str,
    resource: dict,
    alt_resource: dict,
) -> dict:
    model = get_model(provider)
    context = (
        f"Primary:\n{resource.get('excerpt', '')[:2000]}\n\n"
        f"Secondary:\n{alt_resource.get('excerpt', '')[:2000]}"
    )

    system = """You create tutoring topic configs for a freshman/sophomore Software Engineering course.
Return ONLY valid JSON — no markdown fences, no commentary."""

    human = f"""Topic name: {name}

Reading material summaries:
{context}

Audience: first- or second-year undergrads in intro SE. They are beginners — no industry experience.

Generate JSON with exactly these keys:
- practice_label: short default scenario name
- practice_options: exactly 3 short scenario names the student can choose among (relatable).
  First option may match practice_label. No vendor product names.
- practice_prompt: 1-2 sentences for the tutor during practice. Self-directed.
  The student chooses the scenario; the tutor only questions. Avoid AWS/Azure/GCP product names.
- practice_stages: exactly 4 objects with "label" and "focus". Order:
  1) end in mind — what are we designing?
  2) a foundational concept step
  3) a second concept step
  4) wrap-up piece
  Stages must be freshman-friendly.
- final_example: short model answer for wrap-up ONLY if the student asks to see one.

Topic: {name}. Keep everything appropriate for week 1–4 of an intro SE class."""

    response = invoke_with_retry(
        model, [SystemMessage(content=system), HumanMessage(content=human)]
    )
    content = response.content if isinstance(response.content, str) else str(response.content)
    return _parse_json_response(content)


def generate_topic_draft(name: str, provider: str | None = None) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Topic name is required")

    provider = pick_provider(provider)
    primary, alt = _find_two_resources(name)
    llm_part = _llm_fill_topic(name, provider, primary, alt)

    draft = {
        "id": _slugify(name),
        "name": name,
        "resource": {"title": primary["title"], "url": primary["url"]},
        "alt_resource": {"title": alt["title"], "url": alt["url"]},
        "practice_label": llm_part["practice_label"],
        "practice_prompt": llm_part["practice_prompt"],
        "practice_stages": llm_part["practice_stages"],
        "practice_options": llm_part.get("practice_options") or [llm_part["practice_label"]],
        "final_example": llm_part["final_example"],
    }

    return validate_topic(draft)
