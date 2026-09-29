"""Real PostgreSQL tests in a throwaway schema; never touch existing tables."""
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AUTH_MODE", "open")
os.environ.setdefault("REQUIRE_GITHUB_ACCOUNT", "false")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("AUTH_SESSION_SECRET", "test-only-platform-session-secret")
os.environ.setdefault("PLATFORM_SERVICE_TOKEN", "test-only-platform-service-secret")

from platform_app.main import app
from app import auth, db, settings
from platform_app import store


@pytest.fixture(scope="session", autouse=True)
def database():
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    schema = "cluball_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    original = settings.DATABASE_URL
    settings.DATABASE_URL = make_conninfo(dsn, options=f"-c search_path={schema}")
    settings.SCHOOL_GOOGLE_AUTH_ENABLED = False
    settings.REQUIRE_GITHUB_ACCOUNT = False
    settings.OPENAI_API_KEY = ""
    db.init_db()
    store.migrate()
    yield
    settings.DATABASE_URL = original
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def client(database):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def roster(database):
    ids = {k: str(uuid4()) for k in ("prof", "other_prof", "student", "other_student", "course")}
    salt, password_hash = db._hash_password('platform-test-password')
    with store.connection() as conn:
        for key in ("prof", "other_prof", "student", "other_student"):
            uid = ids[key]
            conn.execute("""INSERT INTO users_platform(id,username,email,password_salt,password_hash,authority_level,onboarding_completed_at)
                VALUES (%s,%s,%s,%s,%s,%s,now())""", (uid, uid, f"{uid}@example.test", salt, password_hash, 1 if 'prof' in key else 2))
        conn.execute("INSERT INTO courses_platform(id,course_code,title,instructor_id) VALUES (%s,'SE101','Software Engineering',%s)", (ids['course'], ids['prof']))
        for key in ('prof', 'student', 'other_student'):
            conn.execute("INSERT INTO course_memberships_platform(id,course_id,user_id,course_role,status) VALUES (%s,%s,%s,%s,'approved')",
                         (uuid4(), ids['course'], ids[key], 'instructor' if key == 'prof' else 'student'))
    ids['headers'] = {key: {'Authorization': 'Bearer ' + auth.issue_session(ids[key])[0]} for key in ('prof', 'other_prof', 'student', 'other_student')}
    return ids
