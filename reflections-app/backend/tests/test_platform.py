import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['PLATFORM_SERVICE_TOKEN']='test-service-secret'
os.environ['OPENAI_API_KEY']='test-not-a-real-key'
os.environ['LANGSMITH_TRACING']='false'

@pytest.fixture(scope='module')
def client():
    dsn=os.getenv('TEST_DATABASE_URL')
    if not dsn: pytest.skip('Set TEST_DATABASE_URL to test reflection checkpoints.')
    schema='reflections_test_'+uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    from urllib.parse import quote
    os.environ['DATABASE_URL']=dsn+('?' if '?' not in dsn else '&')+'options='+quote('-c search_path='+schema)
    from app.main import app
    with TestClient(app,headers={'X-Platform-Service':'test-service-secret'}) as c:
        yield c
    from app.database import engine
    engine.dispose()
    with psycopg.connect(dsn,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def config():
    return {'module_type':'topic_based','required_topics':['Design'],'sub_topics':['Requirements'],
            'expected_depth':'applied','probing_style':'supportive','must_include_application':False,
            'custom_notes':'','milestone_prompt':'','historical_data':''}


def test_service_auth_and_immutable_module(client):
    from app.main import app
    assert TestClient(app).get('/api/modules').status_code==401
    mid=str(uuid4()); body={'name':'Reflection assignment','config':config()}
    assert client.put('/internal/platform/modules/'+mid,json=body).status_code==200
    assert client.put('/internal/platform/modules/'+mid,json=body).status_code==200
    body['config']['expected_depth']='surface'
    assert client.put('/internal/platform/modules/'+mid,json=body).status_code==409


def test_start_message_end_retry_and_restart(client,monkeypatch):
    from app.agents import runner
    from app.agents.nodes import planner,tutor,evaluator
    class Model:
        def __init__(self,role): self.role=role
        def generate(self,messages):
            if self.role=='planner': return '["How do requirements guide a design?"]'
            if self.role=='evaluator': return '{"topics_covered":["Requirements"],"missing_topics":[],"misconceptions":[],"reflection_depth_score":3,"confidence_level":4,"engagement_score":3}'
            return '{"adequate":false,"reply":"Can you give a concrete example?"}'
    for module in (planner,tutor,evaluator): monkeypatch.setattr(module,'get_llm_for_role',lambda role:Model(role))
    mid,sid,uid=str(uuid4()),str(uuid4()),str(uuid4())
    response=client.put('/internal/platform/modules/'+mid,json={'name':'Assignment','config':config()})
    assert response.status_code==200,response.text
    body={'session_id':sid,'student_id':uid,'module_id':mid}
    start=client.post('/internal/platform/start',json=body)
    assert start.status_code==200,start.text
    assert client.post('/internal/platform/start',json=body).json()==start.json()
    req={'session_id':sid,'request_id':str(uuid4()),'message':'Requirements describe what the system needs to do.'}
    first=client.post('/internal/platform/message',json=req)
    assert first.status_code==200,first.text
    assert client.post('/internal/platform/message',json=req).json()==first.json()
    before=runner.platform_state(sid)
    runner.teardown_checkpointer();runner.setup_checkpointer()
    assert runner.platform_state(sid)['messages']==before['messages']
    ended=client.post('/internal/platform/end',json={'session_id':sid})
    assert ended.status_code==200,ended.text
    assert ended.json()['evaluation']['reflection_depth_score']==3
    assert client.post('/internal/platform/end',json={'session_id':sid}).json()==ended.json()
