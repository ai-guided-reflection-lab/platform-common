"""Chat model factory — Groq or OpenAI, chosen once per session."""

import re
import time

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

PROVIDERS = {
    "groq": {
        "label": "Groq (GPT-OSS 20B)",
        "model": "groq:openai/gpt-oss-20b",
        "env_key": "GROQ_API_KEY",
        "max_tokens": 400,
    },
    "openai": {
        "label": "OpenAI (GPT-4o mini)",
        "model": "openai:gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "max_tokens": 400,
    },
}

_models: dict[str, BaseChatModel] = {}
_WAIT_RE = re.compile(r"try again in ([0-9.]+)\s*s", re.IGNORECASE)


def get_model(provider: str) -> BaseChatModel:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")

    if provider not in _models:
        spec = PROVIDERS[provider]
        _models[provider] = init_chat_model(
            spec["model"],
            max_tokens=spec.get("max_tokens", 400),
        )

    return _models[provider]


def invoke_with_retry(model: BaseChatModel, messages: list, *, attempts: int = 4):
    """Retry Groq/OpenAI 429 TPM limits using the wait hinted in the error."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return model.invoke(messages)
        except Exception as exc:
            text = str(exc)
            rate_limited = "429" in text or "rate_limit" in text.lower()
            if not rate_limited or attempt == attempts - 1:
                raise
            match = _WAIT_RE.search(text)
            wait = float(match.group(1)) + 0.4 if match else 2.0 * (attempt + 1)
            time.sleep(min(wait, 8.0))
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("invoke_with_retry failed")
