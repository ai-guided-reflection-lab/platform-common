from __future__ import annotations

from typing import Any


async def chat_completion(api_key: str, base_url: str, request: dict[str, Any]) -> Any:
    """Finish an LLM request and close its HTTP transport before its event loop exits."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        return await client.chat.completions.create(**request)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            await close()
