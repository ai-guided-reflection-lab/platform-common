"""Service-boundary checks; no external AI requests or database writes."""
import sys
from pathlib import Path
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Socratic-Chat/backend'))
from fastapi import HTTPException
from platform_app import engines, workspace
from platform_app.schemas import AssignmentInput

class Connections(TestCase):
    def test_student_identity_mapping_is_reused_but_isolated_by_account(self):
        engines._student_identity_cache.clear()
        account={'user_id':'student1','email':'test@example.invalid','username':'student1','display_name':'Test'}
        client=MagicMock()
        client.post.return_value.is_error=False
        client.post.return_value.json.return_value={'id':'mapped-student'}
        with patch.dict('os.environ',{'PLATFORM_SERVICE_TOKEN':'test-service'}), patch.object(engines.httpx,'Client') as factory:
            factory.return_value.__enter__.return_value=client
            self.assertEqual(engines.resolve_self_directed_student(account),'mapped-student')
            self.assertEqual(engines.resolve_self_directed_student(account),'mapped-student')
            self.assertEqual(client.post.call_count,1)
            engines.resolve_self_directed_student({**account,'user_id':'student2'})
            self.assertEqual(client.post.call_count,2)
        engines._student_identity_cache.clear()

    def test_debate_draft_validates_and_snapshot_keeps_scenario(self):
        item=AssignmentInput(course_id='00000000-0000-0000-0000-000000000001',tool='debate',title='Debate',config={'scenario':'Should teams favor simpler software designs?'})
        snapshot=engines.publish_snapshot({'tool':'debate','config':item.config})
        started=engines.start({'tool':'debate','snapshot':snapshot},{})
        self.assertTrue(started['messages'][0]['content'])
        self.assertEqual(snapshot['config']['scenario'],item.config['scenario'])

    def test_debate_message_uses_configured_adapter(self):
        async def reply(*args): return 'What evidence supports that tradeoff?'
        with patch.object(engines.debate,'generate_reply',side_effect=reply):
            result=engines.message({'tool':'debate','snapshot':{'config':{'scenario':'Simple design'}}},{'messages':[]},'Simplicity is easier to maintain.','request')
        self.assertIn('evidence',result['reply'])

    def test_sdl_prepare_uses_selected_chunks_and_persists_plan(self):
        conn=MagicMock()
        @contextmanager
        def connection(): yield conn
        item={'tool':'self-directed-learning','status':'draft','course_id':'course','title':'Requirements','config':{'document_ids':['doc'],'prompt':'Use examples','custom_questions':['What makes a requirement testable?']}}
        plan={'title':'Requirements lesson','objectives':[]}
        with patch.object(workspace.store,'connection',connection), patch.object(workspace,'get_assignment',return_value=item), patch.object(workspace.shared_rag,'course_chunks',return_value=[{'text':'A requirement describes a stakeholder capability or constraint.'}]) as chunks, patch.object(workspace.shared_rag,'pipeline',return_value=plan) as pipeline:
            result=workspace.prepare_sdl('assignment',{'user_id':'professor'})
        chunks.assert_called_once_with('course',['doc'])
        self.assertEqual(pipeline.call_args.args[:2],('POST','/internal/platform/lessons/prepare'))
        self.assertIn('What makes a requirement testable?',pipeline.call_args.kwargs['json']['focus'])
        self.assertEqual(result['learning_plan'],plan)
        self.assertTrue(conn.execute.called)

    def test_aiducate_cannot_publish_without_engine(self):
        with self.assertRaises(HTTPException) as error:
            engines.publish_snapshot({'tool':'aiducate','config':{}})
        self.assertEqual(error.exception.status_code,503)
