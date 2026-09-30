import os,sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'Socratic-Chat' / 'backend'))
from platform_app import routes

@pytest.fixture
def gateway(monkeypatch):
 app=FastAPI();app.include_router(routes.router)
 account={'user_id':'signed-student','username':'Alex','email':'alex@example.test','authority_level':2}
 app.dependency_overrides[routes.user]=lambda: account
 monkeypatch.setattr(routes.engines,'resolve_self_directed_student',lambda supplied: 'resolved-'+supplied['user_id'])
 calls=[]
 def upstream(identity,method,path,**kwargs):
  calls.append((identity,method,path,kwargs));return {'ok':True,'learning_state':{'stage':'welcome'}}
 monkeypatch.setattr(routes.engines,'self_directed_call',upstream)
 with TestClient(app) as client: yield client,calls,account


def test_signed_identity_list_and_full_learning_turn(gateway):
 client,calls,account=gateway
 assert client.get('/api/platform/self-directed/assignments').status_code==200
 assert calls[-1][:3]==('resolved-signed-student','GET','/api/student/assignments')
 body={'turn_id':'same-retry-id','action':'answer','question_id':'Q1','option_index':2,'confidence':'low','explanation':'My reasoning'}
 response=client.post('/api/platform/self-directed/assignments/a/learning-turn',json=body,headers={'X-Demo-User':'another-student'})
 assert response.status_code==200,response.text
 assert calls[-1][:3]==('resolved-signed-student','POST','/api/student/assignments/a/learning-turn')
 assert calls[-1][3]['json']['turn_id']==body['turn_id']
 assert calls[-1][3]['json']['option_index']==2
 assert client.post('/api/platform/self-directed/assignments/a/learning-turn',json={**body,'student_id':'other'}).status_code==422
 assert client.post('/api/platform/self-directed/assignments/a/learning-turn',json={**body,'option_index':True}).status_code==422


def test_professor_cannot_launch_student_identity(gateway):
 client,calls,account=gateway
 account['authority_level']=1
 assert client.get('/api/platform/self-directed/assignments').status_code==403
 assert calls==[]
