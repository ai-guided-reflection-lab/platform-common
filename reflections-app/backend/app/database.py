"""Database configuration — SQLAlchemy engine, session, and base."""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker, declarative_base

# Load .env: root project .env first (shared with docker-compose), then
# backend/.env for local overrides (takes precedence via override=True).
_root = Path(__file__).resolve().parent.parent.parent
_backend = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")
load_dotenv(_backend / ".env", override=not bool(os.getenv("PLATFORM_SERVICE_TOKEN")))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/reflection_chatbot",
)

# Use psycopg v3 dialect (psycopg2 is incompatible with Python 3.14)
# SQLAlchemy requires postgresql+psycopg:// scheme for psycopg v3
sqlalchemy_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {}
if "supabase" in DATABASE_URL:
    connect_args["sslmode"] = "require"

engine = create_engine(sqlalchemy_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        # Quick connectivity check to provide a JSON error if the DB is unreachable
        try:
            db.execute(text("SELECT 1"))
        except OperationalError as oe:
            db.close()
            raise HTTPException(503, f"Database unavailable: {str(oe)}")
        yield db
    finally:
        db.close()
