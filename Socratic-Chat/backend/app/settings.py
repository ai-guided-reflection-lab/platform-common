from __future__ import annotations

import os
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
RAG_TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "0.2"))
CLASSIFIER_ENABLED = os.getenv("CLASSIFIER_ENABLED", "true").lower() in {"1", "true", "yes"}
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "").strip()
CLASSIFIER_TEMPERATURE = float(os.getenv("CLASSIFIER_TEMPERATURE", "0"))
CLASSIFIER_MAX_TOKENS = int(os.getenv("CLASSIFIER_MAX_TOKENS", "900"))
CLASSIFIER_MAX_HISTORY = int(os.getenv("CLASSIFIER_MAX_HISTORY", "6"))
ANSWER_EVALUATION_ENABLED = os.getenv("ANSWER_EVALUATION_ENABLED", "true").lower() in {"1", "true", "yes"}
ANSWER_EVALUATION_MODEL = os.getenv("ANSWER_EVALUATION_MODEL", "").strip()
ANSWER_EVALUATION_MAX_TOKENS = int(os.getenv("ANSWER_EVALUATION_MAX_TOKENS", "1600"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
RAG_MIN_DENSE_SIMILARITY = float(os.getenv("RAG_MIN_DENSE_SIMILARITY", "0.42"))
RAG_MIN_SPARSE_SCORE = float(os.getenv("RAG_MIN_SPARSE_SCORE", "0.05"))
DEBUG_PIPELINE_LOGS = os.getenv("DEBUG_PIPELINE_LOGS", "false").lower() in {"1", "true", "yes"}


DATABASE_URL = os.getenv("DATABASE_URL", "")

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
ALLOWED_GOOGLE_DOMAINS = {
    domain.strip().lower()
    for domain in os.getenv("ALLOWED_GOOGLE_DOMAINS", "").split(",")
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
