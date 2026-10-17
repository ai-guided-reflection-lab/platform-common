"""Course-code enrollment, shared documents, and cross-course authorization."""
from uuid import uuid4
from platform_app import shared_rag, store


def test_anonymous_demo_requires_opt_in_localhost_and_local_database(client, monkeypatch):
    from fastapi.testclient import TestClient
    from platform_app.main import app
    from platform_app import workspace
    from app import settings
    monkeypatch.setattr(workspace, 'test_account_session', lambda role: {'user':{'username':'wiring-'+role},'access_token':'disposable-test-session'})
    monkeypatch.delenv('WIRING_PUBLIC_DEMO', raising=False)
    body = {'role':'student'}
    assert client.post('/api/platform/testing/session', json=body).status_code == 404
    monkeypatch.setenv('WIRING_TEST_MODE','true')
    monkeypatch.setenv('WIRING_PUBLIC_DEMO','true')
    assert client.post('/api/platform/testing/session', json=body).status_code == 404
    with TestClient(app, client=('127.0.0.1',50000)) as local:
        response = local.post('/api/platform/testing/session', json=body)
        assert response.status_code == 200
        assert response.json()['user']['username'] == 'wiring-student'
        monkeypatch.setattr(settings,'DATABASE_URL','postgresql://postgres:unused@example.supabase.co:5432/postgres')
        assert local.post('/api/platform/testing/session',json=body).status_code == 404


def test_profile_updates_only_signed_in_user_without_changing_email(client, roster):
    from app import db
    account = db.get_user_by_id(roster['student'])
    response = client.put('/api/platform/profile', headers=roster['headers']['student'], json={'display_name':'Updated Student','email':account['email']})
    assert response.status_code == 200
    assert db.get_user_by_id(roster['student'])['display_name'] == 'Updated Student'
    assert client.put('/api/platform/profile', headers=roster['headers']['student'], json={'display_name':'Updated Student','email':'unverified@example.test'}).status_code == 422
    assert db.get_user_by_id(roster['student'])['email'] == account['email']


def test_role_switch_is_local_and_disposable_accounts_only(client, roster, monkeypatch):
    from fastapi.testclient import TestClient
    from platform_app.main import app
    headers = roster['headers']['prof']
    assert client.post('/api/platform/testing/role', headers=headers, json={'role':'student'}).status_code == 403
    monkeypatch.setenv('WIRING_TEST_MODE', 'true')
    with TestClient(app, client=('127.0.0.1', 50000)) as local:
        assert local.post('/api/platform/testing/role', headers=headers, json={'role':'student'}).status_code == 403
        with store.connection() as conn:
            conn.execute("UPDATE users_platform SET username='wiring-professor' WHERE id=%s", (roster['prof'],))
            conn.execute("UPDATE users_platform SET username='wiring-student' WHERE id=%s", (roster['student'],))
        response = local.post('/api/platform/testing/role', headers=headers, json={'role':'student'})
        assert response.status_code == 200, response.text
        assert response.json()['user']['authority_level'] == 2
        assert response.json()['access_token']
        assert client.post('/api/platform/testing/role', headers=headers, json={'role':'student'}).status_code == 403


def test_course_code_immediately_joins_and_grants_published_assignments(client, roster):
    professor = roster['headers']['prof']
    created = client.post('/api/platform/courses', headers=professor, json={'title':'New course','course_code':'ITSC 4000'})
    assert created.status_code == 201, created.text
    course = created.json()
    assert len(course['join_code']) == 8
    visible=client.get('/api/platform/courses',headers=roster['headers']['other_student']).json()['courses']
    assert course['course_id'] not in {r['course_id'] for r in visible}
    assignment = client.post('/api/platform/assignments', headers=professor, json={
        'course_id':course['course_id'],'tool':'debate','title':'Debate a course policy','config':{'scenario':'Should every assignment require a written reflection?'}}).json()
    assert client.post(f"/api/platform/assignments/{assignment['id']}/publish",headers=professor).status_code == 200
    student=roster['headers']['other_student']
    assert client.post('/api/platform/courses/join',headers=student,json={'code':course['join_code'].lower()}).status_code == 200
    assert client.post('/api/platform/courses/join',headers=student,json={'code':course['join_code']}).status_code == 200
    assert client.get(f"/api/platform/assignments/{assignment['id']}",headers=student).status_code == 200
    assert client.post('/api/platform/courses/join',headers=professor,json={'code':course['join_code']}).status_code == 403
    assert client.post('/api/platform/courses/join',headers=student,json={'code':'bad'}).status_code == 422


def test_document_upload_uses_sdl_pipeline_and_retrieval_checks_course_scope(client,roster,monkeypatch):
    calls=[]
    def pipeline(method,path,**kwargs):
        calls.append((path,kwargs))
        if path.endswith('/parse'):return {'chunks':[{'text':'A requirement describes expected system behavior.','metadata':{},'page_number':1}]}
        if path.endswith('/embeddings'):
            return {'embeddings':[[1.0]+[0.0]*(shared_rag.embedding_options()['dimensions']-1)]}
        return {'chunks':[{'text':'A requirement describes expected system behavior.','document_id':kwargs['json']['chunks'][0]['document_id']}]}
    monkeypatch.setattr(shared_rag,'pipeline',pipeline)
    path=f"/api/platform/courses/{roster['course']}/documents"
    uploaded=client.post(path+'/upload',headers=roster['headers']['prof'],files={'files':('reading.txt',b'A requirement describes expected system behavior.','text/plain')})
    assert uploaded.status_code == 200,uploaded.text
    file=uploaded.json()['files'][0]
    assert [c[0].rsplit('/',1)[-1] for c in calls] == ['parse','embeddings']
    assert client.get(path,headers=roster['headers']['student']).json()['files'][0]['document_id'] == file['document_id']
    assert client.get(path+f"/{file['id']}/download",headers=roster['headers']['student']).content == b'A requirement describes expected system behavior.'
    body={'course_id':roster['course'],'document_ids':[file['document_id']],'query':'What is a requirement?'}
    found=client.post('/api/platform/rag/search',headers=roster['headers']['student'],json=body)
    assert found.status_code == 200,found.text
    chunks=client.post('/api/platform/rag/chunks',headers=roster['headers']['student'],json=body)
    assert chunks.status_code == 200 and 'embedding' not in chunks.json()['chunks'][0]
    denied=client.post('/api/platform/rag/search',headers=roster['headers']['other_prof'],json=body)
    assert denied.status_code == 404
    assert client.post('/api/platform/rag/search',headers=roster['headers']['student'],json={**body,'document_ids':['another-course-document']}).status_code == 422
    assert client.post(path+'/upload',headers=roster['headers']['student'],files={'files':('x.txt',b'bad')}).status_code == 403


def test_linked_sdl_access_is_revoked_immediately(client,roster,monkeypatch):
    assignment=client.post('/api/platform/assignments',headers=roster['headers']['prof'],json={
        'course_id':roster['course'],'tool':'self-directed-learning','title':'SDL lesson','config':{}}).json()
    with store.connection() as conn:
        conn.execute("UPDATE assignments_platform SET status='published' WHERE id=%s",(assignment['id'],))
        conn.execute('INSERT INTO assignment_recipients_platform VALUES (%s,%s)',(assignment['id'],roster['student']))
        conn.execute("UPDATE course_memberships_platform SET status='rejected' WHERE course_id=%s AND user_id=%s",(roster['course'],roster['student']))
    # No SDL service request is made after enrollment is revoked.
    monkeypatch.setattr(shared_rag,'pipeline',lambda *a,**k: (_ for _ in ()).throw(AssertionError('must not call service')))
    response=client.post(f"/api/platform/self-directed/assignments/{assignment['id']}/start",headers=roster['headers']['student'])
    assert response.status_code == 404,response.text
