import importlib.util
import os
from pathlib import Path
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['PLATFORM_SERVICE_TOKEN'] = 'test-service-secret'
os.environ['OPENAI_API_KEY'] = 'test-not-a-real-key'
os.environ['TUTOR_SESSION_DB'] = str(Path(tempfile.mkdtemp()) / 'sessions.sqlite3')
import app
import tutor
from session_store import SessionStore
from topic_store import get_topic


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'sessions', SessionStore(tmp_path / 'sessions.sqlite3'))
    return TestClient(app.app, headers={'X-Platform-Service':'test-service-secret'})


def test_private_service_rejects_untrusted_requests(client):
    assert TestClient(app.app).get('/api/config').status_code == 401
    assert TestClient(app.app).post('/internal/platform/action', json={}).status_code == 401
    assert TestClient(app.app).get('/health').status_code == 200


def test_session_survives_store_restart_and_topic_edit(client, monkeypatch):
    topic = dict(get_topic('agile_scrum'))
    topic['name'] = 'Frozen topic name'
    body = {'session_id':'durable-session','topic_id':topic['id'],'topic_snapshot':topic,'provider':'openai'}
    started = client.post('/api/session/start', json=body)
    assert started.status_code == 200, started.text
    assert started.json()['topic_name'] == 'Frozen topic name'
    monkeypatch.setattr(app, 'sessions', SessionStore(app.sessions.path))
    resumed = client.get('/api/session/durable-session')
    assert resumed.json()['messages'] == started.json()['messages']
    assert resumed.json()['topic_name'] == 'Frozen topic name'
    assert client.post('/api/session/start',json=body).json()['messages']==started.json()['messages']


def test_mutation_and_retry_response_are_persisted_together(client,monkeypatch):
    client.post('/api/session/start',json={'session_id':'s1','topic_id':'agile_scrum','provider':'openai'})
    calls=[]
    def reply(session,message):
        calls.append(message)
        session.messages.extend([{'role':'user','content':message},{'role':'assistant','content':'Keep thinking'}])
    monkeypatch.setattr(app,'tutor_reply',reply)
    body={'session_id':'s1','request_id':'r1','action':'message','value':'My response'}
    first=client.post('/internal/platform/action',json=body)
    assert first.status_code==200,first.text
    monkeypatch.setattr(app,'sessions',SessionStore(app.sessions.path))
    second=client.post('/internal/platform/action',json=body)
    assert first.json()==second.json()
    assert calls==['My response']


def test_failed_mutation_leaves_original_session(client,monkeypatch):
    original=client.post('/api/session/start',json={'session_id':'s1','topic_id':'agile_scrum','provider':'openai'}).json()
    def failure(session,message):
        session.messages.append({'role':'user','content':message})
        raise ValueError('Try again')
    monkeypatch.setattr(app,'tutor_reply',failure)
    response=client.post('/internal/platform/action',json={'session_id':'s1','request_id':'r1','action':'message','value':'Test'})
    assert response.status_code==422
    assert client.get('/api/session/s1').json()==original


def test_adaptive_endpoints_assess_and_render_without_owning_policy(client, monkeypatch):
    def render(session, decision, objective, prompt, **kwargs):
        if kwargs.get('student_message'):
            session.messages.append({'role':'user','content':kwargs['student_message']})
        session.messages.append({'role':'assistant','content':f"{decision['action']}: {prompt}"})

    monkeypatch.setattr(app, 'render_adaptive_action', render)
    monkeypatch.setattr(app, 'assess_response', lambda provider, objective, assessment, response: {
        'objective_id': assessment['objective_id'],
        'assessment_type': assessment['assessment_type'],
        'correctness': 'correct',
        'completeness': 'complete',
        'independence': 'independent',
        'misconception_code': None,
        'misconception_detail': None,
        'rationale': 'The response demonstrates the requested skill.',
        'assessor_version': 'test-v1',
    })
    objective = {'id':'OBJ-1','description':'Explain classes and objects.'}
    decision = {'action':'ASSESS','objective_id':'OBJ-1','reason_codes':['insufficient_evidence']}
    started = client.post('/internal/platform/adaptive/start', json={
        'session_id':'adaptive-1','provider':'openai','plan_title':'OOP',
        'decision':decision,'objective':objective,'assessment_prompt':'Class or object?',
    })
    assert started.status_code == 200, started.text
    assessed = client.post('/internal/platform/adaptive/assess', json={
        'provider':'openai','objective':objective,
        'assessment':{'objective_id':'OBJ-1','assessment_type':'conceptual'},
        'student_response':'A class is a blueprint and an object is an instance.',
    })
    assert assessed.status_code == 200, assessed.text
    assert assessed.json()['correctness'] == 'correct'

    payload = {
        'session_id':'adaptive-1','request_id':'adaptive-request-1',
        'student_message':'A class is a blueprint.','provider':'openai','plan_title':'OOP',
        'decision':{'action':'ADVANCE','objective_id':'OBJ-1','reason_codes':['objective_demonstrated']},
        'objective':objective,'assessment_prompt':'Read this code.',
        'assessment_result':assessed.json(),'rag_context':[],
    }
    first = client.post('/internal/platform/adaptive/render', json=payload)
    second = client.post('/internal/platform/adaptive/render', json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    assert sum(message['role'] == 'user' for message in first.json()['messages']) == 1
