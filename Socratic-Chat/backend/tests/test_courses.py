from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app import db, main, rag, settings
from app.schemas import ChatRequest, CourseCreateRequest


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


class CourseAuthorizationTests(unittest.TestCase):
    @patch("app.main.db.ensure_conversation")
    @patch("app.main.db.conversation_belongs_to_course", return_value=False)
    def test_stale_conversation_id_is_replaced_for_current_course(
        self,
        _belongs_to_course,
        ensure_conversation,
    ) -> None:
        ensure_conversation.side_effect = ["stale-conversation", "fresh-conversation"]

        conversation_id, replaced = main._ensure_course_conversation(
            "stale-conversation",
            "What is code review?",
            "student-1",
            "course-1",
        )

        self.assertEqual(conversation_id, "fresh-conversation")
        self.assertTrue(replaced)
        self.assertEqual(ensure_conversation.call_count, 2)
        self.assertIsNone(ensure_conversation.call_args_list[1].args[0])

    @patch("app.main.db.ensure_conversation", return_value="current-conversation")
    @patch("app.main.db.conversation_belongs_to_course", return_value=True)
    def test_current_course_conversation_id_is_preserved(
        self,
        _belongs_to_course,
        ensure_conversation,
    ) -> None:
        conversation_id, replaced = main._ensure_course_conversation(
            "current-conversation",
            "What is code review?",
            "student-1",
            "course-1",
        )

        self.assertEqual(conversation_id, "current-conversation")
        self.assertFalse(replaced)
        ensure_conversation.assert_called_once()

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

    @patch("app.main.db.delete_course")
    @patch("app.main._require_authority", return_value={"user_id": "instructor-1"})
    def test_instructor_can_delete_owned_course(self, _require_authority, delete_course) -> None:
        delete_course.return_value = {
            "course_id": "course-1",
            "course_code": "ITCS 3153",
            "title": "Artificial Intelligence",
        }

        response = asyncio.run(main.delete_course("course-1", _request()))

        delete_course.assert_called_once_with("instructor-1", "course-1")
        self.assertEqual(response.course_id, "course-1")
        self.assertIn("permanently deleted", response.message)

    @patch("app.main.db.delete_course", return_value=None)
    @patch("app.main._require_authority", return_value={"user_id": "instructor-1"})
    def test_instructor_cannot_delete_another_instructors_course(
        self,
        _require_authority,
        _delete_course,
    ) -> None:
        with self.assertRaises(HTTPException) as context:
            asyncio.run(main.delete_course("course-2", _request()))

        self.assertEqual(context.exception.status_code, 404)

    @patch("app.db.get_connection")
    @patch("app.db.init_db")
    def test_course_deletion_is_scoped_to_owner(self, _init_db, get_connection) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = ("course-1", "ITCS 3153", "Artificial Intelligence")
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection

        course = db.delete_course("instructor-1", "course-1")

        delete_sql, delete_params = cursor.execute.call_args.args
        self.assertIn("instructor_id = %s", delete_sql)
        self.assertEqual(delete_params, ("course-1", "instructor-1"))
        self.assertEqual(course["course_code"], "ITCS 3153")
        connection.commit.assert_called_once()

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

    @patch("app.rag.db.save_rag_file", return_value="file-a")
    @patch("app.rag.ingest_file", return_value=("doc-a", 1))
    def test_scan_raw_docs_honors_ragignore(self, ingest_file, _save_file) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw_docs = Path(directory)
            (raw_docs / "keep.txt").write_text("Keep this course content.", encoding="utf-8")
            (raw_docs / "private-source.txt").write_text("Do not index this source.", encoding="utf-8")
            (raw_docs / ".ragignore").write_text("private-source.txt\n", encoding="utf-8")
            original_raw_docs = settings.RAW_DOCS_DIR
            settings.RAW_DOCS_DIR = raw_docs
            try:
                documents, chunks, skipped = rag.scan_raw_docs()
            finally:
                settings.RAW_DOCS_DIR = original_raw_docs

        self.assertEqual((documents, chunks, skipped), (1, 1, []))
        self.assertEqual(ingest_file.call_args.args[0].name, "keep.txt")

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.hybrid_search_chunks")
    def test_exact_assignment_filter_is_sent_to_postgres(self, search, _embeddings) -> None:
        search.return_value = [
            {
                "document_id": "assignment-2",
                "chunk_id": "assignment-2:0",
                "title": "course.tex",
                "text": "Assignment 2 - Modular Sandwich Maker. Convert the code into modules.",
                "score": 0.03,
                "dense_similarity": 0.71,
                "sparse_score": 0.18,
            },
        ]

        sources = rag.retrieve("Tell me about Assignment 2", course_id="course-a")

        self.assertEqual(sources[0].document_id, "assignment-2")
        self.assertEqual(sources[0].score, 0.03)
        self.assertEqual(len(sources), 1)
        self.assertEqual(search.call_args.kwargs["assignment_numbers"], {2})

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.hybrid_search_chunks")
    def test_assignment_filter_excludes_cross_references(self, search, _embeddings) -> None:
        search.return_value = [
            {
                "document_id": "assignment-1",
                "chunk_id": "assignment-1:requirements",
                "title": "course-core.html",
                "text": "Assignment 1 > Requirements. Check resources before accepting payment.",
                "metadata": {"assignment_number": 1},
                "score": 0.03,
                "dense_similarity": 0.69,
                "sparse_score": 0.21,
            },
        ]

        sources = rag.retrieve("What are the Assignment 1 payment requirements?", course_id="course-a")

        self.assertEqual([source.document_id for source in sources], ["assignment-1"])
        self.assertEqual(search.call_args.kwargs["assignment_numbers"], {1})

    def test_assignment_range_is_expanded(self) -> None:
        self.assertEqual(rag.requested_assignment_numbers("Compare Assignments 1-5 requirements"), {1, 2, 3, 4, 5})
        self.assertEqual(rag.requested_assignment_numbers("Compare Assignment 1 to 5"), {1, 2, 3, 4, 5})

    def test_assignment_answers_request_a_compact_table(self) -> None:
        instruction = rag.answer_format_instruction("Explain Assignment 1")
        self.assertIn("Markdown table", instruction)
        self.assertIn("Assignment", instruction)
        self.assertIn("Requirements", instruction)

    def test_generation_failure_returns_clean_service_fallback(self) -> None:
        class FailingCompletions:
            async def create(self, **kwargs):
                self.kwargs = kwargs
                raise RuntimeError("temporary API failure")

        completions = FailingCompletions()

        class FakeAsyncOpenAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=completions)

        source = rag.Source(
            document_id="doc-a",
            chunk_id="doc-a:0",
            title="course-notes.txt",
            text="The group project has three parts.",
            score=1.0,
        )
        fake_openai = SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)

        with (
            patch.object(settings, "LLM_PROVIDER", "openai"),
            patch.object(settings, "OPENAI_API_KEY", "test-key"),
            patch.dict(sys.modules, {"openai": fake_openai}),
            self.assertLogs("app.rag", level="ERROR"),
        ):
            answer = asyncio.run(rag.generate_answer("What is version control?", [], [source]))

        self.assertEqual(
            answer,
            "I found relevant course material, but I could not generate the explanation right now. Please try again.",
        )
        self.assertNotIn("reasoning_effort", completions.kwargs)

    def test_openai_gpt_4_1_mini_generates_tutor_responses(self) -> None:
        created_clients = []

        class SuccessfulCompletions:
            async def create(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="What evidence supports that idea?"))]
                )

        completions = SuccessfulCompletions()

        class FakeAsyncOpenAI:
            def __init__(self, **kwargs):
                created_clients.append(kwargs)
                self.chat = SimpleNamespace(completions=completions)

        source = rag.Source(
            document_id="doc-a",
            chunk_id="doc-a:0",
            title="course-notes.txt",
            text="Version control records changes over time.",
            score=1.0,
        )
        fake_openai = SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)

        with (
            patch.object(settings, "LLM_PROVIDER", "openai"),
            patch.object(settings, "OPENAI_API_KEY", "openai-test-key"),
            patch.object(settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
            patch.object(settings, "RAG_MODEL", "gpt-4.1-mini"),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            answer = asyncio.run(rag.generate_answer("What is version control?", [], [source]))

        self.assertTrue(answer)
        self.assertEqual(created_clients[0]["api_key"], "openai-test-key")
        self.assertEqual(created_clients[0]["base_url"], "https://api.openai.com/v1")
        self.assertEqual(completions.kwargs["model"], "gpt-4.1-mini")

    def test_model_unsupported_response_is_not_turned_into_a_socratic_question(self) -> None:
        class UnsupportedCompletions:
            async def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(
                        content="That topic is outside the currently published course documentation."
                    ))]
                )

        class FakeAsyncOpenAI:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=UnsupportedCompletions())

        source = rag.Source(
            document_id="doc-a", chunk_id="doc-a:0", title="course-notes.txt",
            text="Software projects use code review.", score=1.0,
        )
        with (
            patch.object(settings, "LLM_PROVIDER", "openai"),
            patch.object(settings, "OPENAI_API_KEY", "test-key"),
            patch.dict(sys.modules, {"openai": SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)}),
        ):
            answer = asyncio.run(rag.generate_answer("Explain sushi recipes", [], [source]))

        self.assertEqual(
            answer,
            "That topic is outside the currently published course documentation.",
        )

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.replace_document_chunks", return_value=1)
    def test_latex_document_is_cleaned_and_chunked(self, replace_chunks, _embeddings) -> None:
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
            _, chunks_added = rag.ingest_file(path, course_id="course-a", file_id="file-a")

        indexed = replace_chunks.call_args.args[3]
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

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.hybrid_search_chunks")
    def test_retrieval_returns_only_selected_course_chunks(self, search, _embeddings) -> None:
        search.return_value = [
            {
                "document_id": "doc-a",
                "chunk_id": "doc-a:0",
                "title": "A.txt",
                "text": "linear regression model",
                "score": 0.02,
                "dense_similarity": 0.76,
                "sparse_score": 0.14,
            },
        ]
        sources = rag.retrieve("linear regression", course_id="course-a")
        self.assertEqual([source.document_id for source in sources], ["doc-a"])
        self.assertEqual(search.call_args.kwargs["course_id"], "course-a")

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.hybrid_search_chunks")
    def test_unrelated_dense_candidates_are_rejected(self, search, _embeddings) -> None:
        search.return_value = [
            {
                "document_id": "chapter-13",
                "chunk_id": "chapter-13:0",
                "title": "ch13.html",
                "text": "Build systems and software engineering practices.",
                "score": 1 / 61,
                "dense_similarity": 0.19,
                "sparse_score": 0.0,
            },
            {
                "document_id": "chapter-17",
                "chunk_id": "chapter-17:0",
                "title": "ch17.html",
                "text": "Developer tools at scale.",
                "score": 1 / 62,
                "dense_similarity": 0.16,
                "sparse_score": 0.0,
            },
        ]

        sources = rag.retrieve("sushi recipe", course_id="course-a")

        self.assertEqual(sources, [])

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.hybrid_search_chunks")
    def test_sparse_evidence_keeps_a_relevant_result_with_lower_dense_similarity(
        self, search, _embeddings,
    ) -> None:
        search.return_value = [
            {
                "document_id": "chapter-9",
                "chunk_id": "chapter-9:review",
                "title": "ch09.html",
                "text": "Code review requires another engineer to examine a change before submission.",
                "score": 0.03,
                "dense_similarity": 0.35,
                "sparse_score": 0.24,
            },
        ]

        sources = rag.retrieve("code review", course_id="course-a")

        self.assertEqual([source.document_id for source in sources], ["chapter-9"])

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.hybrid_search_chunks")
    def test_incidental_weak_sparse_match_is_rejected(self, search, _embeddings) -> None:
        search.return_value = [
            {
                "document_id": "chapter-13",
                "chunk_id": "chapter-13:0",
                "title": "ch13.html",
                "text": "A software project uses a documented process.",
                "score": 0.02,
                "dense_similarity": 0.21,
                "sparse_score": 0.01,
            },
        ]
        self.assertEqual(rag.retrieve("sushi recipe", course_id="course-a"), [])

    def test_no_relevant_sources_stop_before_llm_generation(self) -> None:
        with patch("app.rag.generation_client_config") as client_config:
            answer = asyncio.run(rag.generate_answer("What is a sushi recipe?", [], []))

        client_config.assert_not_called()
        self.assertEqual(
            answer,
            "That topic is outside the currently published course documentation.",
        )

    def test_course_metadata_answers_do_not_depend_on_document_search(self) -> None:
        course = {
            "course_code": "ITCS 3155",
            "title": "Software Engineering",
            "description": "Software design and teamwork",
            "instructor_name": "Demo Instructor",
        }
        files = [{"filename": "course-paper.pdf"}]
        self.assertEqual(
            main._operational_context_answer(
                course,
                files,
                main.MessageClassification(operational_request="course_instructor"),
            ),
            "The instructor for ITCS 3155 is Demo Instructor.",
        )
        scope = main._operational_context_answer(
            course,
            files,
            main.MessageClassification(operational_request="course_scope"),
        )
        self.assertIn("Software Engineering", scope)
        self.assertIn("course-paper.pdf", scope)

    def test_learning_statement_that_mentions_files_does_not_list_documents(self) -> None:
        course = {
            "course_code": "ITCS 3155",
            "title": "Software Engineering",
            "description": "Software design and teamwork",
            "instructor_name": "Demo Instructor",
        }
        files = [{"filename": "ch19.html"}]
        classification = main.MessageClassification(
            route="learning",
            student_intent="reflection",
            operational_request="none",
        )
        self.assertIsNone(main._operational_context_answer(course, files, classification))

    def test_document_list_uses_classifier_intent_not_message_keywords(self) -> None:
        course = {
            "course_code": "ITCS 3155",
            "title": "Software Engineering",
            "description": "",
            "instructor_name": "Demo Instructor",
        }
        files = [{"filename": "ch19.html"}, {"filename": "ch20.html"}]
        classification = main.MessageClassification(
            route="administrative",
            operational_request="list_documents",
        )
        answer = main._operational_context_answer(course, files, classification)
        self.assertEqual(answer, "Published course documents: ch19.html, ch20.html.")

if __name__ == "__main__":
    unittest.main()
