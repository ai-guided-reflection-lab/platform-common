import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.llm_client import chat_completion


class LlmClientLifecycleTests(unittest.TestCase):
    def test_closes_client_after_success(self):
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value="reply"))),
            close=AsyncMock(),
        )
        with patch("openai.AsyncOpenAI", return_value=client):
            result = asyncio.run(chat_completion("local", "http://localhost", {"model": "test"}))
        self.assertEqual(result, "reply")
        client.close.assert_awaited_once()

    def test_closes_client_after_request_failure(self):
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("request failed")))),
            close=AsyncMock(),
        )
        with patch("openai.AsyncOpenAI", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                asyncio.run(chat_completion("local", "http://localhost", {"model": "test"}))
        client.close.assert_awaited_once()
