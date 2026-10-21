import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest
from app import objective_extraction

class ExtractionTests(unittest.TestCase):

    def test_keyword_suggestions_rank_repeated_concept_phrases(self) -> None:
        chunks = [
            {
                "text": (
                    "Unit testing isolates code dependencies. "
                    "Unit testing makes failures easier to diagnose."
                ),
            },
            {
                "text": (
                    "Integration testing checks services together. "
                    "Unit testing and integration testing serve different purposes."
                ),
            },
        ]

        keywords = objective_extraction.suggest_keywords(chunks)

        self.assertIn("unit testing", keywords)
        self.assertIn("integration testing", keywords)
        self.assertLessEqual(len(keywords), 12)

    def test_extraction_keeps_only_real_source_chunks_and_saves_drafts(self) -> None:
        chunks = [{
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "title": "testing.html",
            "text": "Students should distinguish public behavior from implementation details.",
            "metadata": {},
        }]
        model_payload = {
            "objectives": [{
                "keywords": ["public API", "test stability"],
                "objective": "Explain why tests should focus on public behavior.",
                "prerequisites": ["unit tests"],
                "success_criteria": ["Connects stability to public behavior"],
                "common_misconceptions": ["Every internal method needs a direct test"],
                "diagnostic_question": "Which test is likely to remain stable",
                "source_chunk_ids": ["chunk-1", "invented-chunk"],
                "confidence": 0.9,
                "evidence_type": "explicit",
            }],
        }
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(model_payload)),
        )])
        with (
            patch("app.objective_extraction.db.get_document_chunks_for_objectives", return_value=chunks),
            patch("app.objective_extraction.settings.llm_client_config", return_value=(
                "Ollama", "ollama", "http://127.0.0.1:11434/v1", "qwen",
            )),
            patch("app.objective_extraction.chat_completion", new_callable=AsyncMock, return_value=response),
            patch("app.objective_extraction.db.replace_document_learning_objectives", return_value=1) as save,
        ):
            count = asyncio.run(objective_extraction.extract_and_save_learning_objectives("file-1", "course-1"))

        self.assertEqual(count, 1)
        saved = save.call_args.args[2][0]
        self.assertEqual(saved["source_chunk_ids"], ["chunk-1"])
        self.assertEqual(saved["keywords"], ["public API", "test stability"])
        self.assertNotIn("title", saved)
        self.assertNotIn("starting_scenario", saved)
        self.assertEqual(saved["diagnostic_question"], "Which test is likely to remain stable?")

    def test_extraction_drops_objectives_without_valid_evidence(self) -> None:
        payload = {"objectives": [{
            "keywords": ["Unsupported idea"],
            "objective": "Explain an unsupported topic.",
            "prerequisites": [],
            "success_criteria": [],
            "common_misconceptions": [],
            "diagnostic_question": "What happens?",
            "source_chunk_ids": ["not-supplied"],
            "confidence": 1,
            "evidence_type": "inferred",
        }]}
        self.assertEqual(objective_extraction._validated_objectives(payload, {"chunk-1"}), [])

    def test_ollama_uses_a_larger_context_batch_and_smaller_output_budget(self) -> None:
        chunks = [
            {
                "chunk_id": f"chunk-{index}",
                "chunk_index": index,
                "title": "testing.html",
                "text": "A" * 10_000,
                "metadata": {},
            }
            for index in range(5)
        ]
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps({"objectives": []})),
        )])
        with (
            patch("app.objective_extraction.db.get_document_chunks_for_objectives", return_value=chunks),
            patch("app.objective_extraction.settings.llm_client_config", return_value=(
                "Ollama", "ollama", "http://127.0.0.1:11434/v1", "qwen",
            )),
            patch(
                "app.objective_extraction.chat_completion",
                new_callable=AsyncMock,
                return_value=response,
            ) as completion,
            patch("app.objective_extraction.db.replace_document_learning_objectives", return_value=0),
        ):
            asyncio.run(objective_extraction.extract_and_save_learning_objectives("file-1", "course-1"))

        self.assertEqual(completion.await_count, 1)
        request = completion.await_args.args[2]
        self.assertEqual(
            request["max_tokens"],
            objective_extraction.OLLAMA_OBJECTIVE_COMPLETION_TOKENS,
        )
        self.assertEqual(
            request["response_format"]["json_schema"]["schema"]["properties"]["objectives"]["maxItems"],
            objective_extraction.OLLAMA_OBJECTIVES_PER_BATCH,
        )
        self.assertLess(
            len(request["messages"][1]["content"]),
            len(chunks) * 11_000,
        )

    def test_extraction_retries_a_malformed_model_response(self) -> None:
        chunks = [{
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "title": "testing.html",
            "text": "Students should explain unit testing.",
            "metadata": {},
        }]
        valid_payload = {"objectives": [{
            "keywords": ["unit testing"],
            "objective": "Explain unit testing.",
            "prerequisites": [],
            "success_criteria": [],
            "common_misconceptions": [],
            "diagnostic_question": "What does a unit test verify?",
            "source_chunk_ids": ["chunk-1"],
            "confidence": 0.9,
            "evidence_type": "explicit",
        }]}
        malformed = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"objectives":['),
        )])
        valid = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(valid_payload)),
        )])
        with (
            patch("app.objective_extraction.db.get_document_chunks_for_objectives", return_value=chunks),
            patch("app.objective_extraction.settings.llm_client_config", return_value=(
                "Groq", "key", "https://example.invalid", "openai/gpt-oss-120b",
            )),
            patch(
                "app.objective_extraction.chat_completion",
                new_callable=AsyncMock,
                side_effect=[malformed, valid],
            ) as completion,
            patch("app.objective_extraction.db.replace_document_learning_objectives", return_value=1),
        ):
            count = asyncio.run(objective_extraction.extract_and_save_learning_objectives("file-1", "course-1"))

        self.assertEqual(count, 1)
        self.assertEqual(completion.await_count, 2)
        request = completion.await_args_list[0].args[2]
        self.assertEqual(request["max_completion_tokens"], objective_extraction.OBJECTIVE_COMPLETION_TOKENS)
        self.assertEqual(request["reasoning_effort"], "low")

    def test_extraction_saves_successful_batches_when_one_batch_fails(self) -> None:
        chunks = [
            {
                "chunk_id": "chunk-1",
                "chunk_index": 0,
                "title": "testing.html",
                "text": "A" * objective_extraction.MAX_BATCH_CHARS,
                "metadata": {},
            },
            {
                "chunk_id": "chunk-2",
                "chunk_index": 1,
                "title": "testing.html",
                "text": "Students should explain integration testing.",
                "metadata": {},
            },
        ]
        valid_payload = {"objectives": [{
            "keywords": ["unit testing"],
            "objective": "Explain unit testing.",
            "prerequisites": [],
            "success_criteria": [],
            "common_misconceptions": [],
            "diagnostic_question": "What does a unit test verify?",
            "source_chunk_ids": ["chunk-1"],
            "confidence": 0.9,
            "evidence_type": "explicit",
        }]}
        valid = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(valid_payload)),
        )])
        with (
            patch("app.objective_extraction.db.get_document_chunks_for_objectives", return_value=chunks),
            patch("app.objective_extraction.settings.llm_client_config", return_value=(
                "Groq", "key", "https://example.invalid", "model",
            )),
            patch(
                "app.objective_extraction.chat_completion",
                new_callable=AsyncMock,
                side_effect=[valid, ValueError("bad JSON"), ValueError("bad JSON")],
            ),
            patch("app.objective_extraction.db.replace_document_learning_objectives", return_value=1) as save,
        ):
            count = asyncio.run(objective_extraction.extract_and_save_learning_objectives("file-1", "course-1"))

        self.assertEqual(count, 1)
        self.assertEqual(save.call_args.args[2][0]["source_chunk_ids"], ["chunk-1"])

    def test_near_duplicate_objectives_are_merged(self) -> None:
        first = {
            "keywords": ["code review"], "objective": "Explain the purpose of code review.",
            "prerequisites": [], "success_criteria": ["Names correctness"],
            "common_misconceptions": [],
            "diagnostic_question": "What should Sam inspect?", "source_chunk_ids": ["chunk-1"],
            "confidence": 0.9, "evidence_type": "explicit",
        }
        second = {
            **first,
            "source_chunk_ids": ["chunk-2"],
            "success_criteria": ["Names maintainability"],
            "confidence": 0.8,
        }
        merged = objective_extraction._merge_objectives([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source_chunk_ids"], ["chunk-1", "chunk-2"])
        self.assertEqual(merged[0]["success_criteria"], ["Names correctness", "Names maintainability"])
