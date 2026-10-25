"""Provider failures are reported safely without making live model requests."""
import os
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from openai import AuthenticationError

from app.services.llm import GroqProvider, OpenAIProvider, LLMConfigurationError
from app.main import app


class ProviderErrorTests(unittest.TestCase):
    def test_namespaced_role_provider_takes_precedence_and_legacy_still_works(self):
        from app.services import llm
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "TUTOR_LLM_PROVIDER": "openai",
                                    "REFLECTIONS_TUTOR_LLM_PROVIDER": "groq"}), patch.object(llm, 'GroqProvider') as groq:
            self.assertIs(llm.get_llm_for_role('tutor'), groq.return_value)
        with patch.dict(os.environ, {"REFLECTIONS_TUTOR_LLM_PROVIDER": "", "TUTOR_LLM_PROVIDER": "openai"}), patch.object(llm, 'OpenAIProvider') as openai:
            self.assertIs(llm.get_llm_for_role('tutor'), openai.return_value)

    def test_missing_key(self):
        for cls, name in [(GroqProvider, 'GROQ_API_KEY'), (OpenAIProvider, 'OPENAI_API_KEY')]:
            with self.subTest(provider=name), patch.dict(os.environ, {name: ' '}):
                with self.assertRaises(LLMConfigurationError):
                    cls()

    def test_rejected_credentials_do_not_leak_upstream_body(self):
        for cls in (GroqProvider, OpenAIProvider):
            provider = cls.__new__(cls)
            provider.model = 'test-model'
            provider.client = Mock()
            response = httpx.Response(401, request=httpx.Request('POST', 'https://provider.example/chat'))
            provider.client.chat.completions.create.side_effect = AuthenticationError(
                'secret-provider-response', response=response, body={'secret': 'hidden'},
            )
            with self.assertRaises(LLMConfigurationError) as error:
                provider.generate([{'role': 'user', 'content': 'Hello'}])
            self.assertNotIn('secret', str(error.exception))

    def test_start_reports_configuration_error_without_logging_student_out(self):
        from app.agents import runner
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: Mock()
        with patch.dict(os.environ, {'PLATFORM_SERVICE_TOKEN': 'test-service-secret'}), patch.object(
            runner, 'platform_state', side_effect=LLMConfigurationError('secret-provider-response'),
        ):
            response = TestClient(app).post('/internal/platform/start',
                headers={'X-Platform-Service': 'test-service-secret'}, json={
                    'session_id': '00000000-0000-0000-0000-000000000001',
                    'student_id': '00000000-0000-0000-0000-000000000002',
                    'module_id': '00000000-0000-0000-0000-000000000003',
                    'course_id': '00000000-0000-0000-0000-000000000004',
                })
        app.dependency_overrides.pop(get_db, None)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'llm_authentication_failed')
        self.assertIn('API key', response.json()['detail'])
        self.assertNotIn('secret', response.text)


if __name__ == '__main__':
    unittest.main()
