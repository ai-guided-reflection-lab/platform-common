from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app import db, main, rag, settings
from app.schemas import ChatRequest, CourseCreateRequest


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


class CourseAuthorizationTests(unittest.TestCase):
    @patch("app.main._current_user_id", return_value="student-1")
    def test_chat_requires_a_selected_course(self, _current_user_id) -> None:
        with self.assertRaises(HTTPException) as context:
            asyncio.run(main.chat(ChatRequest(message="What is regression?"), _request()))
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("approved course", context.exception.detail)

    @patch("app.main.db.user_can_access_course", return_value=False)
    @patch("app.main.db.get_user_by_id", return_value={"user_id": "student-1"})
    @patch("app.main._current_user_id", return_value="student-1")
    def test_pending_student_cannot_access_course(
        self,
        _current_user_id,
        _get_user,
        _can_access,
    ) -> None:
        with self.assertRaises(HTTPException) as context:
            main._require_course_access(_request(), "course-1")
        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("approved", context.exception.detail)

    @patch("app.main.db.create_course")
    @patch("app.main._require_authority", return_value={"user_id": "instructor-1"})
    def test_instructor_can_create_course(self, _require_authority, create_course) -> None:
        create_course.return_value = {
            "course_id": "course-1",
            "course_code": "ITCS 3153",
            "title": "Artificial Intelligence",
            "description": "Course materials",
            "instructor_id": "instructor-1",
            "instructor_name": "Professor One",
            "membership_role": None,
            "membership_status": None,
            "document_count": 0,
            "pending_request_count": 0,
        }
        response = asyncio.run(
            main.create_course(
                CourseCreateRequest(
                    course_code="ITCS 3153",
                    title="Artificial Intelligence",
                    description="Course materials",
                ),
                _request(),
            )
        )
        self.assertEqual(response.membership_role, "instructor")
        self.assertEqual(response.membership_status, "approved")

    @patch("app.main.db.remove_course_student")
    @patch("app.main._require_authority", return_value={"user_id": "instructor-1"})
    def test_instructor_can_remove_approved_student(self, _require_authority, remove_student) -> None:
        remove_student.return_value = {
            "membership_id": "membership-1",
            "course_id": "course-1",
            "user_id": "student-1",
            "display_name": "Student One",
            "email": "student@charlotte.edu",
            "course_role": "student",
            "status": "approved",
            "requested_at": "2026-08-25T12:00:00Z",
        }

        response = asyncio.run(main.remove_enrolled_course_student("membership-1", _request()))

        remove_student.assert_called_once_with("instructor-1", "membership-1")
        self.assertEqual(response.user_id, "student-1")
        self.assertEqual(response.status, "approved")

    @patch("app.db.get_connection")
    @patch("app.db.init_db")
    def test_student_removal_is_scoped_to_own_course(self, _init_db, get_connection) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            "membership-1",
            "course-1",
            "student-1",
            "Student One",
            "student@charlotte.edu",
            "student",
            "approved",
            "2026-08-25T12:00:00Z",
        )
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        membership = db.remove_course_student("instructor-1", "membership-1")

        delete_sql, delete_params = cursor.execute.call_args.args
        self.assertIn("c.instructor_id = %s", delete_sql)
        self.assertIn("cm.status = 'approved'", delete_sql)
        self.assertEqual(delete_params, ("membership-1", "instructor-1"))
        self.assertEqual(membership["user_id"], "student-1")


class CourseRagIsolationTests(unittest.TestCase):
    def test_numbered_assignment_tokens_keep_the_identifier(self) -> None:
        self.assertEqual(rag.tokenize("Tell me about Assignment 2"), ["assignment", "2"])

    @patch("app.rag.load_index")
    def test_exact_assignment_number_is_boosted_even_with_an_old_index(self, load_index) -> None:
        load_index.return_value = [
            {
                "document_id": "assignment-1",
                "chunk_id": "assignment-1:0",
                "course_id": "course-a",
                "title": "course.tex",
                "text": "Assignment 1 - Sandwich Maker. Build an interactive sandwich machine.",
                "tokens": ["assignment", "sandwich", "maker"],
            },
            {
                "document_id": "assignment-2",
                "chunk_id": "assignment-2:0",
                "course_id": "course-a",
                "title": "course.tex",
                "text": "Assignment 2 - Modular Sandwich Maker. Convert the code into modules.",
                "tokens": ["assignment", "modular", "sandwich", "maker"],
            },
        ]

        sources = rag.retrieve("Tell me about Assignment 2", course_id="course-a")

        self.assertEqual(sources[0].document_id, "assignment-2")
        self.assertEqual(sources[0].score, 1.0)

    def test_assignment_answers_request_a_compact_table(self) -> None:
        instruction = rag.answer_format_instruction("Explain Assignment 1")
        self.assertIn("Markdown table", instruction)
        self.assertIn("Assignment", instruction)
        self.assertIn("Requirements", instruction)

    @patch("app.rag.save_index")
    @patch("app.rag.load_index", return_value=[])
    def test_latex_document_is_cleaned_and_chunked(self, _load_index, save_index) -> None:
        latex = r"""
        \documentclass{article}
        % This comment must not enter the RAG index.
        \title{Private Retrieval Systems}
        \begin{document}
        \section{Introduction}
        Retrieval-augmented generation uses \textbf{external evidence}.
        \begin{equation}
        E = mc^2
        \end{equation}
        \end{document}
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lecture.tex"
            path.write_text(latex, encoding="utf-8")
            _, chunks_added = rag.ingest_file(path, course_id="course-a")

        indexed = save_index.call_args.args[0]
        indexed_text = " ".join(item["text"] for item in indexed)
        self.assertEqual(chunks_added, 1)
        self.assertIn("Private Retrieval Systems", indexed_text)
        self.assertIn("external evidence", indexed_text)
        self.assertIn("E = mc^2", indexed_text)
        self.assertNotIn("documentclass", indexed_text)
        self.assertNotIn("This comment", indexed_text)

    def test_same_document_in_different_courses_gets_different_ids(self) -> None:
        first = rag.document_id("syllabus.pdf", "same text", course_id="course-a")
        second = rag.document_id("syllabus.pdf", "same text", course_id="course-b")
        self.assertNotEqual(first, second)

    @patch("app.rag.load_index")
    def test_retrieval_returns_only_selected_course_chunks(self, load_index) -> None:
        load_index.return_value = [
            {
                "document_id": "doc-a",
                "chunk_id": "doc-a:0",
                "course_id": "course-a",
                "title": "A.txt",
                "text": "linear regression model",
                "tokens": ["linear", "regression", "model"],
            },
            {
                "document_id": "doc-b",
                "chunk_id": "doc-b:0",
                "course_id": "course-b",
                "title": "B.txt",
                "text": "linear regression model",
                "tokens": ["linear", "regression", "model"],
            },
        ]
        sources = rag.retrieve("linear regression", course_id="course-a")
        self.assertEqual([source.document_id for source in sources], ["doc-a"])

    def test_course_metadata_answers_do_not_depend_on_document_search(self) -> None:
        course = {
            "course_code": "ITCS 3155",
            "title": "Software Engineering",
            "description": "Software design and teamwork",
            "instructor_name": "Demo Instructor",
        }
        files = [{"filename": "course-paper.pdf"}]
        self.assertEqual(
            main._course_context_answer(course, files, "What is the professor name?"),
            "The instructor for ITCS 3155 is Demo Instructor.",
        )
        scope = main._course_context_answer(course, files, "What do you know?")
        self.assertIn("Software Engineering", scope)
        self.assertIn("course-paper.pdf", scope)

    @patch("app.main.ingest_file", return_value=("doc-a", 7))
    @patch("app.main.db.get_rag_file", return_value={"content": b"course notes"})
    @patch("app.main.course_document_ids", return_value=set())
    def test_missing_render_index_is_rebuilt_from_postgres(
        self,
        _document_ids,
        _get_file,
        ingest_file,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_raw_docs = settings.RAW_DOCS_DIR
            settings.RAW_DOCS_DIR = Path(directory)
            try:
                restored = main._restore_missing_course_chunks(
                    "course-a",
                    [{"file_id": "file-a", "document_id": "doc-a", "filename": "notes.txt"}],
                )
            finally:
                settings.RAW_DOCS_DIR = original_raw_docs
        self.assertEqual(restored, 7)
        self.assertEqual(ingest_file.call_args.kwargs["course_id"], "course-a")


if __name__ == "__main__":
    unittest.main()
