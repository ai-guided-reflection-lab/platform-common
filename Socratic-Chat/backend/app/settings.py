from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
RAW_DOCS_DIR = BACKEND_DIR / "data" / "raw_docs"

load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
RAG_MODEL = os.getenv("RAG_MODEL", "gpt-4.1-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")
OLLAMA_CLASSIFIER_MODEL = os.getenv("OLLAMA_CLASSIFIER_MODEL", "").strip()
OLLAMA_ANSWER_EVALUATION_MODEL = os.getenv("OLLAMA_ANSWER_EVALUATION_MODEL", "").strip()
OLLAMA_GENERATION_MAX_TOKENS = int(os.getenv("OLLAMA_GENERATION_MAX_TOKENS", "600"))
# Instructor authoring is deliberately independent of all student model roles.
PLATFORM_AGENT_PROVIDER = os.getenv("PLATFORM_AGENT_PROVIDER", "ollama").strip().lower()
PLATFORM_AGENT_API_BASE_URL = os.getenv("PLATFORM_AGENT_API_BASE_URL", "http://127.0.0.1:11434/v1").strip()
PLATFORM_AGENT_API_KEY = os.getenv("PLATFORM_AGENT_API_KEY", "ollama")
PLATFORM_AGENT_MODEL = os.getenv("PLATFORM_AGENT_MODEL", "qwen3.5:9b-q4_K_M").strip()
PLATFORM_AGENT_TIMEOUT_SECONDS = float(os.getenv("PLATFORM_AGENT_TIMEOUT_SECONDS", "60"))
PLATFORM_AGENT_MAX_TOOL_TURNS = int(os.getenv("PLATFORM_AGENT_MAX_TOOL_TURNS", "4"))
PLATFORM_AGENT_MAX_TOOL_CALLS = int(os.getenv("PLATFORM_AGENT_MAX_TOOL_CALLS", "6"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_BASE_URL = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_CLASSIFIER_MODEL = os.getenv("GROQ_CLASSIFIER_MODEL", "").strip()
GROQ_ANSWER_EVALUATION_MODEL = os.getenv("GROQ_ANSWER_EVALUATION_MODEL", "").strip()
RAG_TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "0.2"))
CLASSIFIER_ENABLED = os.getenv("CLASSIFIER_ENABLED", "true").lower() in {"1", "true", "yes"}
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "").strip()
CLASSIFIER_TEMPERATURE = float(os.getenv("CLASSIFIER_TEMPERATURE", "0"))
CLASSIFIER_MAX_TOKENS = int(os.getenv("CLASSIFIER_MAX_TOKENS", "900"))
CLASSIFIER_MAX_HISTORY = int(os.getenv("CLASSIFIER_MAX_HISTORY", "6"))
ANSWER_EVALUATION_ENABLED = os.getenv("ANSWER_EVALUATION_ENABLED", "true").lower() in {"1", "true", "yes"}
ANSWER_EVALUATION_MODEL = os.getenv("ANSWER_EVALUATION_MODEL", "").strip()
ANSWER_EVALUATION_MAX_TOKENS = int(os.getenv("ANSWER_EVALUATION_MAX_TOKENS", "1600"))
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "qwen3-embedding:0.6b" if EMBEDDING_PROVIDER in {"local", "ollama"} else "text-embedding-3-small",
)
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024" if EMBEDDING_PROVIDER in {"local", "ollama"} else "1536"))
EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "120"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
RAG_MIN_DENSE_SIMILARITY = float(os.getenv("RAG_MIN_DENSE_SIMILARITY", "0.42"))
RAG_MIN_SPARSE_SCORE = float(os.getenv("RAG_MIN_SPARSE_SCORE", "0.05"))
DEBUG_PIPELINE_LOGS = os.getenv("DEBUG_PIPELINE_LOGS", "false").lower() in {"1", "true", "yes"}
_pipeline_log_file = os.getenv("PIPELINE_LOG_FILE", "").strip()
PIPELINE_LOG_FILE = (ROOT_DIR / _pipeline_log_file) if _pipeline_log_file else None
LOG_FULL_PROMPTS = os.getenv("LOG_FULL_PROMPTS", "false").lower() in {"1", "true", "yes"}
_pipeline_prompt_dir = os.getenv("PIPELINE_PROMPT_DIR", "").strip()
PIPELINE_PROMPT_DIR = (ROOT_DIR / _pipeline_prompt_dir) if _pipeline_prompt_dir else None
_pipeline_trace_file = os.getenv("PIPELINE_TRACE_FILE", "storage/pipeline-traces.json").strip()
PIPELINE_TRACE_FILE = (BACKEND_DIR / _pipeline_trace_file) if _pipeline_trace_file else None


def platform_agent_client_config() -> tuple[str, str, str, str] | None:
    """Never fall back to a tutor provider, even when authoring is disabled."""
    if PLATFORM_AGENT_PROVIDER not in {"ollama", "local"}:
        raise ValueError("PLATFORM_AGENT_PROVIDER must be ollama or local.")
    if not PLATFORM_AGENT_MODEL or not PLATFORM_AGENT_API_BASE_URL:
        return None
    return "Ollama", PLATFORM_AGENT_API_KEY or "ollama", PLATFORM_AGENT_API_BASE_URL, PLATFORM_AGENT_MODEL


def completion_token_parameters(provider: str, limit: int) -> dict[str, int | str]:
    """Use the output-token parameter supported by the hosted providers."""
    if provider == "Ollama":
        return {"max_tokens": limit, "reasoning_effort": "none"}
    return {"max_completion_tokens": limit}


def embedding_client_config() -> tuple[str, str, str, str] | None:
    """Configure document/query embeddings independently of conversational models."""
    if EMBEDDING_PROVIDER in {"local", "ollama"}:
        return "Ollama", OLLAMA_API_KEY or "ollama", OLLAMA_API_BASE_URL, EMBEDDING_MODEL
    if EMBEDDING_PROVIDER != "openai":
        raise ValueError("EMBEDDING_PROVIDER must be openai or ollama.")
    if not OPENAI_API_KEY:
        return None
    return "OpenAI", OPENAI_API_KEY, OPENAI_API_BASE_URL, EMBEDDING_MODEL


def embedding_model_name() -> str:
    return EMBEDDING_MODEL


def llm_client_config(role: str = "generation") -> tuple[str, str, str, str] | None:
    """Return the configured chat provider, independently of embedding settings."""
    if LLM_PROVIDER in {"local", "ollama"}:
        role_model = {
            "classifier": OLLAMA_CLASSIFIER_MODEL,
            "evaluation": OLLAMA_ANSWER_EVALUATION_MODEL,
        }.get(role, "")
        return "Ollama", OLLAMA_API_KEY or "ollama", OLLAMA_API_BASE_URL, role_model or OLLAMA_MODEL
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            return None
        role_model = {
            "classifier": GROQ_CLASSIFIER_MODEL,
            "evaluation": GROQ_ANSWER_EVALUATION_MODEL,
        }.get(role, "")
        return "Groq", GROQ_API_KEY, GROQ_API_BASE_URL, role_model or GROQ_MODEL
    if not OPENAI_API_KEY:
        return None
    role_model = {
        "classifier": CLASSIFIER_MODEL,
        "evaluation": ANSWER_EVALUATION_MODEL,
    }.get(role, "")
    return "OpenAI", OPENAI_API_KEY, OPENAI_API_BASE_URL, role_model or RAG_MODEL


DATABASE_URL = os.getenv("DATABASE_URL", "")


def _schema_name(variable: str, default: str) -> str:
    value = os.getenv(variable, default).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"{variable} must be a valid PostgreSQL identifier.")
    return value


PLATFORM_DB_SCHEMA = _schema_name("PLATFORM_DB_SCHEMA", "platform")
SOCRATIC_DB_SCHEMA = _schema_name("SOCRATIC_DB_SCHEMA", "socratic_chat")
SHARED_RAG_DB_SCHEMA = _schema_name("SHARED_RAG_DB_SCHEMA", "shared_rag")

REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() in {"1", "true", "yes"}
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
EMAIL_CODE_EXPIRY_MINUTES = int(os.getenv("EMAIL_CODE_EXPIRY_MINUTES", "10"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

AUTH_MODE = os.getenv("AUTH_MODE", "open").strip().lower()
SCHOOL_GOOGLE_AUTH_ENABLED = AUTH_MODE == "school_google"
SCHOOL_GITHUB_AUTH_ENABLED = AUTH_MODE == "school_github"
RESTRICTED_SCHOOL_AUTH_ENABLED = SCHOOL_GOOGLE_AUTH_ENABLED or SCHOOL_GITHUB_AUTH_ENABLED
ALLOWED_GOOGLE_DOMAINS = {
    domain.strip().lower()
    for domain in os.getenv("ALLOWED_GOOGLE_DOMAINS", "").split(",")
    if domain.strip()
}
ALLOWED_GITHUB_EMAIL_DOMAINS = {
    domain.strip().lower()
    for domain in os.getenv(
        "ALLOWED_GITHUB_EMAIL_DOMAINS",
        os.getenv("ALLOWED_GOOGLE_DOMAINS", ""),
    ).split(",")
    if domain.strip()
}
AUTH_SESSION_SECRET = os.getenv("AUTH_SESSION_SECRET", "")
AUTH_SESSION_MINUTES = int(os.getenv("AUTH_SESSION_MINUTES", "60"))
ALLOW_PASSWORD_LOGIN = os.getenv("ALLOW_PASSWORD_LOGIN", "true").lower() in {"1", "true", "yes"}
CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}

REQUIRE_GITHUB_ACCOUNT = os.getenv("REQUIRE_GITHUB_ACCOUNT", "false").lower() in {"1", "true", "yes"}
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_CALLBACK_URL = os.getenv("GITHUB_CALLBACK_URL", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://jamesonthehill.com/Socratic-Chat/")

LTI_CANVAS_ISSUER = os.getenv("LTI_CANVAS_ISSUER", "").strip().rstrip("/")
CANVAS_API_ORIGIN = os.getenv("CANVAS_API_ORIGIN", "https://instructure.charlotte.edu").strip().rstrip("/")
LTI_PUBLIC_BASE_URL = os.getenv("LTI_PUBLIC_BASE_URL", "").strip().rstrip("/")
LTI11_CONSUMER_KEY = os.getenv("LTI11_CONSUMER_KEY", "").strip()
LTI11_SHARED_SECRET = os.getenv("LTI11_SHARED_SECRET", "")
LTI_AUTO_CREATE_ASSIGNMENTS = os.getenv("LTI_AUTO_CREATE_ASSIGNMENTS", "true").lower() in {"1", "true", "yes"}
