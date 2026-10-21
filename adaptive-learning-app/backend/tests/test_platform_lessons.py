from copy import deepcopy
from test_api import client, lesson


def payload():
    plan = lesson()
    plan['content_approved'] = True
    return {'id':'platform-course-lesson','title':'Course lesson','instructions':'Read and practice.',
            'instructor':{'id':'prof-platform','email':'prof@example.test','display_name':'Professor'},
            'students':[{'id':'student-platform','email':'learner@example.test','display_name':'Learner'}],
            'learning_plan':plan,
            'chunks':[{'document_id':'shared-document','title':'Reading.txt','text':'Requirements describe system behavior.','embedding':[1.0,0.0]}]}


def test_platform_lesson_requires_service_auth_and_publishes_idempotently(client,monkeypatch):
    monkeypatch.setenv('PLATFORM_SERVICE_TOKEN','bridge-test-token')
    body=payload()
    path='/internal/platform/lessons/publish'
    assert client.post(path,json=body).status_code == 401
    headers={'X-Platform-Service':'bridge-test-token'}
    published=client.post(path,headers=headers,json=body)
    assert published.status_code == 200,published.text
    assert client.post(path,headers=headers,json=body).json()==published.json()
    detail=client.get('/api/student/assignments/platform-course-lesson',headers={'X-Demo-User':'student-platform'})
    assert detail.status_code == 200,detail.text
    assert 'approved_material' not in detail.json()['learning_plan']
    from app.db import connection
    with connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM documents WHERE assignment_id=?',(body['id'],)).fetchone()['n']==1
    # A late enrollee receives the same immutable lesson without duplicating its documents.
    body['students'].append({'id':'late-platform','email':'late@example.test','display_name':'Late Student'})
    assert client.post(path,headers=headers,json=body).status_code == 200
    assert client.get('/api/student/assignments/platform-course-lesson',headers={'X-Demo-User':'late-platform'}).status_code == 200
    progress=client.get('/internal/platform/lessons/platform-course-lesson/progress',headers=headers)
    assert len(progress.json()) == 2


def test_incomplete_lesson_and_conflicting_identity_are_rejected(client,monkeypatch):
    monkeypatch.setenv('PLATFORM_SERVICE_TOKEN','bridge-test-token')
    body=payload();headers={'X-Platform-Service':'bridge-test-token'}
    bad=deepcopy(body);bad['learning_plan']['diagnostic_quiz']=[]
    assert client.post('/internal/platform/lessons/publish',headers=headers,json=bad).status_code == 422
    body['students'][0]['email']='instructor@example.com'
    # Use a real existing instructor identity from the seeded database.
    from app.db import connection
    with connection() as conn:
        row=conn.execute("SELECT email FROM users WHERE role='instructor' LIMIT 1").fetchone()
    body['students'][0]['email']=row['email']
    assert client.post('/internal/platform/lessons/publish',headers=headers,json=body).status_code == 409
