from __future__ import annotations

import unittest
from unittest.mock import patch

from app.chunking import (
    COURSE_CORE_PROFILE,
    REFERENCE_BOOK_PROFILE,
    approximate_token_count,
    chunk_document,
)
from app import rag
from app.rag import RAG_DOCUMENT_SUFFIXES


class StructuredChunkingTests(unittest.TestCase):
    def test_html_is_supported_for_instructor_uploads(self) -> None:
        self.assertIn(".html", RAG_DOCUMENT_SUFFIXES)
        self.assertIn(".htm", RAG_DOCUMENT_SUFFIXES)

    def test_course_sections_become_separate_chunks_with_breadcrumbs(self) -> None:
        html = """
        <html><head><style>.secret { color: red; }</style></head><body>
        <h1>Software Engineering 3155</h1>
        <h2>Assignment 1</h2>
        <h3>Requirements</h3><p>Check resources before accepting payment.</p>
        <h3>Rubric</h3><p>The program must run without hard-coding.</p>
        </body></html>
        """

        chunks = chunk_document("software-engineering-3155-core.html", html, source_format="html")

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].profile, COURSE_CORE_PROFILE.name)
        self.assertEqual(chunks[0].assignment_number, 1)
        self.assertEqual(chunks[0].section_path[-1], "Requirements")
        self.assertEqual(chunks[1].section_path[-1], "Rubric")
        self.assertIn("Software Engineering 3155 > Assignment 1 > Requirements", chunks[0].text)
        self.assertNotIn("color: red", " ".join(chunk.text for chunk in chunks))

    def test_course_core_article_id_supplies_assignment_metadata(self) -> None:
        html = """
        <html><body><h1>Software Engineering 3155</h1>
        <article id="assignment-2">
          <h2>Modular Ham Sandwich Maker Machine</h2>
          <h3>Requirements</h3><p>Separate payment from sandwich production.</p>
        </article>
        </body></html>
        """

        chunks = chunk_document("software-engineering-3155-core.html", html, source_format="html")

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].assignment_number, 2)

    def test_reference_book_preserves_code_and_does_not_cross_sections(self) -> None:
        paragraph = "Software changes over time and engineers must evaluate trade-offs. " * 80
        html = f"""
        <html><head><title>Software Engineering at Google</title></head><body>
        <h1>What Is Software Engineering?</h1>
        <h2>Time and Change</h2><p>{paragraph}</p>
        <pre>for item in values:\n    print(item)</pre>
        <h2>Scale and Efficiency</h2><p>{paragraph}</p>
        </body></html>
        """

        chunks = chunk_document("ch01.html", html, source_format="html")

        self.assertTrue(chunks)
        self.assertTrue(all(chunk.profile == REFERENCE_BOOK_PROFILE.name for chunk in chunks))
        self.assertTrue(all(chunk.token_count <= REFERENCE_BOOK_PROFILE.max_tokens for chunk in chunks))
        self.assertTrue(any("for item in values:\n print(item)" in chunk.text for chunk in chunks))
        self.assertFalse(
            any("Time and Change" in chunk.section_path and "Scale and Efficiency" in chunk.section_path for chunk in chunks)
        )

    def test_metadata_token_count_matches_chunk_text(self) -> None:
        chunks = chunk_document("notes.md", "# Testing\n\nA test should verify observable behavior.")
        self.assertEqual(chunks[0].token_count, approximate_token_count(chunks[0].text))

    @patch("app.rag.create_embeddings", return_value=[[0.1] * 1536])
    @patch("app.rag.db.replace_document_chunks", return_value=1)
    def test_reingestion_replaces_postgres_chunks(self, replace_chunks, _embeddings) -> None:
        title = "software-engineering-3155-core.html"
        content = "<html><body><h1>Software Engineering 3155</h1><h2>Policy</h2><p>Use evidence.</p></body></html>"
        document_id = rag.document_id(title, content, course_id="course-a")
        _, chunks_added = rag.ingest_text(title, content, course_id="course-a", file_id="file-a")

        saved = replace_chunks.call_args.args[3]
        self.assertEqual(chunks_added, 1)
        self.assertEqual(replace_chunks.call_args.args[1], document_id)
        replacement = saved[0]
        self.assertIn("assignment_number", replacement["metadata"])


if __name__ == "__main__":
    unittest.main()
