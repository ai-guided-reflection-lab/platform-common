from openai import OpenAI

from app import settings


def local_client(factory=OpenAI):
    config = settings.platform_agent_client_config()
    if not config:
        raise ValueError("Platform agent is disabled")
    _, api_key, base_url, model = config
    return factory(api_key=api_key, base_url=base_url,
                   timeout=max(1, settings.PLATFORM_AGENT_TIMEOUT_SECONDS), max_retries=0), model
