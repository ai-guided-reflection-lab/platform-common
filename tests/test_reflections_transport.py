import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from platform_app.reflections_transport import request_reflections


class ReflectionsTransportTests(unittest.TestCase):
    def test_cold_gateway_waits_for_json_health_then_replays_generation(self):
        calls = []
        responses = [httpx.Response(502), httpx.Response(200, text='Loading'),
                     httpx.Response(200, json={'status': 'ok'}),
                     httpx.Response(200, json={'sub_topics': ['actors']})]
        def handle(request):
            calls.append((request.method, request.url.path, request.content))
            return responses.pop(0)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client, patch('platform_app.reflections_transport.sleep'):
            result = request_reflections(client, 'POST', 'https://engine.test', '/api/modules/subtopics/generate', json={'main_topics': ['requirements']})
        self.assertEqual(result.json(), {'sub_topics': ['actors']})
        self.assertEqual([c[:2] for c in calls], [('POST', '/api/modules/subtopics/generate'), ('GET', '/health'), ('GET', '/health'), ('POST', '/api/modules/subtopics/generate')])
        self.assertEqual(calls[0][2], calls[-1][2])

    def test_application_errors_and_other_writes_are_not_replayed(self):
        for status, path in [(500, '/api/modules/subtopics/generate'), (503, '/api/modules/subtopics/generate'), (502, '/internal/platform/modules/id')]:
            with self.subTest(status=status, path=path):
                calls = []
                def handle(request):
                    calls.append(request)
                    return httpx.Response(status, json={'code': 'llm_authentication_failed'})
                with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                    result = request_reflections(client, 'POST', 'https://engine.test', path)
                self.assertEqual(result.status_code, status)
                self.assertEqual(len(calls), 1)

    def test_wakeup_is_bounded_and_gives_actionable_error(self):
        calls = []
        def handle(request):
            calls.append(request.url.path)
            return httpx.Response(502)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client, patch('platform_app.reflections_transport.monotonic', side_effect=[0, 0, 0, 90, 90]):
            with self.assertRaises(HTTPException) as caught:
                request_reflections(client, 'POST', 'https://engine.test', '/api/modules/subtopics/generate')
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn('do not need to redeploy', caught.exception.detail)
        self.assertEqual(calls, ['/api/modules/subtopics/generate', '/health'])


if __name__ == '__main__':
    unittest.main()
