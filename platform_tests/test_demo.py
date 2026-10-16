from uuid import uuid4

from platform_app import demo, store


def demo_entry(client, username, password):
    response = client.post('/api/platform/demo/enter', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    data = response.json()
    return data, {'Authorization': 'Bearer ' + data['access_token']}


def test_demo_disabled_unless_opted_in_and_isolated(client, monkeypatch):
    monkeypatch.delenv('PLATFORM_DEMO_MODE', raising=False)
    assert client.get('/api/platform/demo/config').json() == {'enabled': False}
    body = {'username': 'anyone', 'password': 'random'}
    assert client.post('/api/platform/demo/enter', json=body).status_code == 404
    monkeypatch.setenv('PLATFORM_DEMO_MODE', 'true')
    # The fixture's regular schema is not a demo deployment.
    assert client.post('/api/platform/demo/enter', json=body).status_code == 404


def test_same_combo_restores_profile_and_different_combo_isolated(client, monkeypatch):
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    name = 'visitor-' + uuid4().hex
    first, professor = demo_entry(client, name, 'one')
    again, _ = demo_entry(client, name, 'one')
    different, other = demo_entry(client, name, 'two')
    assert first['user']['user_id'] == again['user']['user_id']
    assert first['user']['user_id'] != different['user']['user_id']
    assert first['demo_mode'] is True
    course = client.post('/api/platform/courses', headers=professor, json={
        'title': 'Private demo course', 'course_code': 'DEMO'}).json()
    assert client.get('/api/platform/courses', headers=other).json()['courses'] == []
    assert client.get(f"/api/platform/courses/{course['course_id']}/documents", headers=other).status_code == 404
    student = client.post('/api/platform/demo/role', headers=professor, json={'role': 'student'})
    assert student.status_code == 200
    assert student.json()['user']['authority_level'] == 2
    student_headers = {'Authorization': 'Bearer ' + student.json()['access_token']}
    assert client.post('/api/platform/courses', headers=student_headers, json={'title': 'No', 'course_code': 'NO'}).status_code == 403
    assert client.post('/api/platform/courses/join', headers=student_headers, json={'code': course['join_code']}).status_code == 200
    back = client.post('/api/platform/demo/role', headers=student_headers, json={'role': 'professor'})
    assert back.json()['user']['user_id'] == first['user']['user_id']
    assert client.get('/api/platform/courses', headers=professor).json()['courses'][0]['course_id'] == course['course_id']
    with store.connection() as conn:
        hashes = conn.execute('SELECT password_hash FROM demo_profiles_platform WHERE username=%s', (name,)).fetchall()
    assert len(hashes) == 2
    assert all(row['password_hash'] not in {'one', 'two'} for row in hashes)


def test_regular_accounts_cannot_use_demo_role_switch(client, roster, monkeypatch):
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    assert client.post('/api/platform/demo/role', headers=roster['headers']['student'], json={'role': 'professor'}).status_code == 403
    assert client.post('/api/platform/demo/role', json={'role': 'professor'}).status_code == 401
