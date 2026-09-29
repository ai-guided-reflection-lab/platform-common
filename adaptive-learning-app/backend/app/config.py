from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


APP_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = APP_ROOT.parent
_PROCESS_ENV_KEYS = set(os.environ)
load_dotenv(WORKSPACE_ROOT / ".env")
for _key, _value in dotenv_values(APP_ROOT / ".env").items():
    if _key not in _PROCESS_ENV_KEYS and _value is not None:
        os.environ[_key] = _value

DATA_DIR = Path(os.getenv("ADAPTIVE_DATA_DIR", APP_ROOT / "data")).resolve()
DATABASE_PATH = Path(os.getenv("ADAPTIVE_DATABASE_PATH", DATA_DIR / "adaptive.sqlite3")).resolve()
DATABASE_URL = "" if os.getenv("ADAPTIVE_DATABASE_PATH") else os.getenv("DATABASE_URL", "")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "self_directed_learning")
UPLOAD_DIR = Path(os.getenv("ADAPTIVE_UPLOAD_DIR", DATA_DIR / "uploads")).resolve()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", os.getenv("ADAPTIVE_AI_MODE", "openai" if os.getenv("OPENAI_API_KEY") else "demo")).lower()
AI_MODE = os.getenv("ADAPTIVE_AI_MODE", LLM_PROVIDER).lower()
ALLOW_DEMO_FALLBACK = os.getenv("ADAPTIVE_ALLOW_DEMO_FALLBACK", "true").lower() in {"1", "true", "yes"}
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

INSTRUCTOR_ORIGIN = os.getenv("INSTRUCTOR_ORIGIN", "http://127.0.0.1:5173")
STUDENT_ORIGIN = os.getenv("STUDENT_ORIGIN", "http://127.0.0.1:5174")


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
