"""Exercise the catalog SQL in PostgreSQL without the unrelated RAG migrations."""
import os
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from platform_app.main import app  # Initialize the gateway import path.
from platform_app import routes


def test_catalog_shared_across_instructors_but_not_students(monkeypatch):
    dsn = os.getenv('TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set TEST_DATABASE_URL for catalog SQL regression test')
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # Temporary tables shadow app tables and disappear on connection close.
        conn.execute('CREATE TEMP TABLE courses_platform (id uuid, title text, course_code text, instructor_id uuid)')
        conn.execute('CREATE TEMP TABLE assignments_platform (id uuid, course_id uuid, creator_id uuid, title text, tool text, status text, config jsonb, snapshot jsonb, created_at timestamptz DEFAULT now(), due_at timestamptz)')
        conn.execute('CREATE TEMP TABLE course_memberships_platform (course_id uuid, user_id uuid, course_role text, status text)')
        conn.execute('CREATE TEMP TABLE assignment_recipients_platform (assignment_id uuid, student_id uuid)')
        conn.execute('CREATE TEMP TABLE assignment_attempts_platform (assignment_id uuid, student_id uuid, status text)')
        owner, colleague, outsider, student, course, other_course, assignment, other_assignment = [uuid4() for _ in range(8)]
        conn.execute("INSERT INTO courses_platform VALUES (%s,'Course','CS101',%s),(%s,'Other course','CS202',%s)", (course, owner, other_course, outsider))
        conn.execute("INSERT INTO assignments_platform (id,course_id,creator_id,title,tool,status,config) VALUES (%s,%s,%s,'Colleague activity','reflections','draft','{\"custom_notes\":\"private\"}'),(%s,%s,%s,'Other course activity','reflections','draft','{}')", (assignment, course, colleague, other_assignment, other_course, outsider))
        for uid in (owner, colleague):
            conn.execute("INSERT INTO course_memberships_platform VALUES (%s,%s,'instructor','approved')", (course, uid))

        @contextmanager
        def connection():
            yield conn
        monkeypatch.setattr(routes.store, 'connection', connection)
        for uid in (owner, colleague, outsider):
            items = routes.assignments(course_id=None, account={'user_id': str(uid), 'authority_level': 1})
            assert {str(a['id']) for a in items} == {str(assignment), str(other_assignment)}
            item = next(a for a in items if a['id'] == assignment)
            assert item['can_manage'] == (uid != outsider)
            if uid == outsider:
                assert 'config' not in item and 'snapshot' not in item
        assert routes.assignments(course_id=None, account={'user_id': str(student), 'authority_level': 2}) == []
