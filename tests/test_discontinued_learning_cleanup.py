"""Verify the deployment deletion targets only the discontinued learning data."""
from pathlib import Path
import re
import sqlite3


def test_cleanup_removes_discontinued_work_without_touching_other_learning():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE assignments_platform(id TEXT PRIMARY KEY,tool TEXT);
        CREATE TABLE assignment_attempts_platform(id TEXT PRIMARY KEY,assignment_id TEXT REFERENCES assignments_platform(id));
        CREATE TABLE assignment_recipients_platform(assignment_id TEXT REFERENCES assignments_platform(id) ON DELETE CASCADE,student_id TEXT);
        CREATE TABLE sdl_assignments(id TEXT PRIMARY KEY);
        INSERT INTO assignments_platform VALUES ('socratic-course','socratic'),('reflection-course','reflections'),('removed-course','discontinued-learning');
        INSERT INTO assignment_attempts_platform VALUES ('socratic-attempt','socratic-course'),('reflection-attempt','reflection-course'),('removed-attempt','removed-course');
        INSERT INTO assignment_recipients_platform VALUES ('socratic-course','student'),('reflection-course','student'),('removed-course','student');
        INSERT INTO sdl_assignments VALUES ('independent-sdl-lesson');
    """)
    migration = (Path(__file__).parents[1] / "platform_app/migrations/005_remove_discontinued_learning.sql").read_text()
    for statement in re.findall(r"DELETE FROM .*?;", migration, re.S):
        connection.execute(statement)
    assert connection.execute("SELECT id FROM assignments_platform ORDER BY id").fetchall() == [('reflection-course',), ('socratic-course',)]
    assert connection.execute("SELECT id FROM assignment_attempts_platform ORDER BY id").fetchall() == [('reflection-attempt',), ('socratic-attempt',)]
    assert connection.execute("SELECT assignment_id FROM assignment_recipients_platform ORDER BY assignment_id").fetchall() == [('reflection-course',), ('socratic-course',)]
    assert connection.execute("SELECT id FROM sdl_assignments").fetchall() == [('independent-sdl-lesson',)]
    connection.close()
