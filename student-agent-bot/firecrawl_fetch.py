"""Optional Firecrawl scrape to preview a reading URL when adding topics."""

import os
import re

from firecrawl import FirecrawlApp


def fetch_url_preview(url: str, max_chars: int = 3000) -> dict:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY not set in env file")

    app = FirecrawlApp(api_key=api_key)
    response = app.scrape_url(url, formats=["markdown"])

    if hasattr(response, "success") and not response.success:
        raise RuntimeError("Firecrawl could not fetch that URL")

    markdown = ""
    title = url

    if hasattr(response, "markdown") and response.markdown:
        markdown = response.markdown
    elif hasattr(response, "data") and response.data:
        data = response.data
        if isinstance(data, dict):
            markdown = data.get("markdown") or data.get("content") or ""
            meta = data.get("metadata") or {}
            title = meta.get("title") or data.get("title") or title
        else:
            markdown = str(data)
    elif isinstance(response, dict):
        markdown = response.get("markdown", "")
        title = response.get("metadata", {}).get("title", title)

    if hasattr(response, "metadata") and response.metadata:
        title = getattr(response.metadata, "title", None) or response.metadata.get("title", title)

    markdown = re.sub(r"\n{3,}", "\n\n", markdown.strip())
    excerpt = markdown[:max_chars]
    if len(markdown) > max_chars:
        excerpt += "\n\n… (truncated)"

    return {
        "url": url,
        "title": title,
        "excerpt": excerpt,
        "char_count": len(markdown),
    }
