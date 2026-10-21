"""Exercise signed assignment launches against PostgreSQL and real platform APIs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from app import settings
from platform_app import lti, lti11, store
from platform_tests.test_lti11 import configured_lti11, exchange, launch, signed


def assignment_launch(client, values=None, **kwargs):
    body, headers = signed(values, url=settings.LTI_PUBLIC_BASE_URL + lti11.ASSIGNMENT_LAUNCH_PATH, **kwargs)
    return client.post(lti11.ASSIGNMENT_LAUNCH_PATH, content=body, headers=headers, follow_redirects=False)


def assignment(conn, assignment_id):
    return conn.execute('SELECT * FROM assignments_platform WHERE id=%s', (assignment_id,)).fetchone()


def test_instructor_creates_draft_reopens_without_overwriting_and_student_opens_published(
    client, configured_lti11, monkeypatch,
):
    params = {
        'user_id': str(uuid4()), 'context_id': str(uuid4()), 'resource_link_id': 'assignment-link',
        'resource_link_title': 'Code review',
        'custom_canvas_assignment_id': '616423',
        'custom_canvas_assignment_title': 'Canvas code review',
        'custom_canvas_assignment_description': '<p>Explain the review.</p><script>ignore this</script>',
        'custom_canvas_assignment_due_at': '2026-11-01T12:00:00Z',
    }
    teacher = exchange(client, assignment_launch(client, params))
    aid = teacher['assignment_id']
    assert aid
    assert teacher['redirect_path'] == (
        f"/platform/professor/activities/{aid}?course={teacher['course_id']}"
    )
    with store.connection() as conn:
        item = assignment(conn, aid)
        assert item['status'] == 'draft'
        assert item['tool'] is None
        assert item['title'] == 'Canvas code review'
        assert item['instructions'] == 'Explain the review.'
        assert item['due_at'] == datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        assert item['config'] == {}
        conn.execute('UPDATE assignments_platform SET title=%s WHERE id=%s', ('Instructor edited title', aid))
    repeated = exchange(client, assignment_launch(client, {
        **params,
        'custom_canvas_assignment_title': 'Updated Canvas title',
        'custom_canvas_assignment_due_at': '2026-12-02T15:30:00Z',
    }))
    assert repeated['assignment_id'] == aid
    with store.connection() as conn:
        updated = assignment(conn, aid)
        assert updated['title'] == 'Updated Canvas title'
        assert updated['due_at'] == datetime(2026, 12, 2, 15, 30, tzinfo=timezone.utc)
        assert conn.execute('SELECT count(*) AS n FROM assignments_platform WHERE course_id=%s', (teacher['course_id'],)).fetchone()['n'] == 1
    student_params = {**params, 'user_id': str(uuid4()), 'roles': 'Learner'}
    pending = assignment_launch(client, student_params)
    assert pending.status_code == 409
    assert 'publish' in pending.json()['detail']
    headers = {'Authorization': 'Bearer ' + teacher['access_token']}
    assert client.post(f'/api/platform/assignments/{aid}/publish', headers=headers).status_code == 422
    chosen = client.put(f'/api/platform/assignments/{aid}', headers=headers, json={
        'course_id': teacher['course_id'], 'tool': 'socratic', 'title': 'Instructor edited title',
        'instructions': 'Explain the review.', 'audience': 'course', 'config': {},
    })
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()['tool'] == 'socratic'
    monkeypatch.setattr('platform_app.engines.publish_snapshot', lambda item: {'config': item['config'], 'chunks': []})
    assert client.post(f'/api/platform/assignments/{aid}/publish', headers=headers).status_code == 200
    student = exchange(client, assignment_launch(client, student_params))
    assert student['assignment_id'] == aid
    assert student['redirect_path'] == f'/platform/student/assignments/{aid}'
    student_headers = {'Authorization': 'Bearer ' + student['access_token']}
    assert client.get(f'/api/platform/assignments/{aid}', headers=student_headers).status_code == 200
    assert client.post(f'/api/platform/assignments/{aid}/start', headers=student_headers).status_code == 200


def test_navigation_with_unexpanded_substitutions_creates_no_assignment(client, configured_lti11):
    result = exchange(client, launch(client, {
        'custom_canvas_assignment_id': '$Canvas.assignment.id',
        'custom_canvas_assignment_title': '$Canvas.assignment.title',
        'resource_link_title': 'ClubALL',
    }))
    assert result['assignment_id'] is None
    with store.connection() as conn:
        assert not conn.execute('SELECT 1 FROM assignments_platform WHERE course_id=%s', (result['course_id'],)).fetchone()


def test_old_launch_url_accepts_assignment_custom_fields_and_graded_launches(client, configured_lti11):
    for marker in ({'custom_canvas_assignment_id': '9'}, {'lis_outcome_service_url': 'https://canvas.example/outcomes'}):
        result = exchange(client, launch(client, {**marker, 'resource_link_title': 'Review'}))
        assert result['assignment_id']


def test_new_path_signature_cannot_be_replayed_on_navigation_path(client, configured_lti11):
    body, headers = signed(url=settings.LTI_PUBLIC_BASE_URL + lti11.ASSIGNMENT_LAUNCH_PATH)
    assert client.post(lti11.LAUNCH_PATH, content=body, headers=headers).status_code == 401
    assert client.post(lti11.ASSIGNMENT_LAUNCH_PATH, content=body, headers=headers, follow_redirects=False).status_code == 303
    assert client.post(lti11.ASSIGNMENT_LAUNCH_PATH, content=body, headers=headers).status_code == 401


def test_student_cannot_create_assignment_in_existing_course(client, configured_lti11):
    context = str(uuid4())
    teacher = exchange(client, launch(client, {'context_id': context}))
    subject = str(uuid4())
    response = assignment_launch(client, {'context_id': context, 'user_id': subject, 'roles': 'Learner'})
    assert response.status_code == 409
    with store.connection() as conn:
        assert not conn.execute('SELECT 1 FROM assignments_platform WHERE course_id=%s', (teacher['course_id'],)).fetchone()
        assert not conn.execute('SELECT 1 FROM lti_identities_platform WHERE subject=%s', (subject,)).fetchone()


def test_assignment_ids_are_scoped_to_course_and_registration(client, configured_lti11, monkeypatch):
    context = str(uuid4())
    params = {'context_id': context, 'resource_link_id': 'same-link', 'custom_canvas_assignment_id': '9'}
    first = exchange(client, assignment_launch(client, params))
    other_course = exchange(client, assignment_launch(client, {**params, 'context_id': str(uuid4())}))
    monkeypatch.setattr(settings, 'LTI11_CONSUMER_KEY', 'other-registration')
    other_registration = exchange(client, assignment_launch(client, params))
    assert len({first['assignment_id'], other_course['assignment_id'], other_registration['assignment_id']}) == 3


def test_parallel_launches_create_one_assignment(configured_lti11):
    claims = lti11._claims({
        'user_id': str(uuid4()), 'context_id': str(uuid4()), 'roles': 'Instructor',
        'resource_link_id': 'parallel-link', 'custom_canvas_assignment_id': '42',
    })
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: lti._provision_launch(claims, deployment_id='lti11'), range(2)))
    assert results[0][1] == results[1][1]
    with store.connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM assignments_platform WHERE course_id=%s', (results[0][1],)).fetchone()['n'] == 1


def test_archived_and_selected_assignments_are_not_exposed_to_unassigned_students(client, configured_lti11):
    params = {'user_id': str(uuid4()), 'context_id': str(uuid4()), 'resource_link_id': 'restricted'}
    teacher = exchange(client, assignment_launch(client, params))
    aid = teacher['assignment_id']
    student_params = {**params, 'user_id': str(uuid4()), 'roles': 'Learner'}
    with store.connection() as conn:
        conn.execute("UPDATE assignments_platform SET tool='socratic', status='published', audience='selected' WHERE id=%s", (aid,))
    assert assignment_launch(client, student_params).status_code == 403
    with store.connection() as conn:
        conn.execute("UPDATE assignments_platform SET status='archived' WHERE id=%s", (aid,))
    assert assignment_launch(client, params).status_code == 409
    assert assignment_launch(client, student_params).status_code == 409


def test_setting_can_disable_assignment_creation(client, configured_lti11, monkeypatch):
    monkeypatch.setattr(settings, 'LTI_AUTO_CREATE_ASSIGNMENTS', False)
    result = exchange(client, assignment_launch(client))
    assert result['assignment_id'] is None
    assert client.get('/api/lti/status').json()['assignment_auto_creation_enabled'] is False


def test_same_link_cannot_be_rebound_to_another_canvas_assignment(client, configured_lti11):
    params = {'user_id': str(uuid4()), 'context_id': str(uuid4()), 'resource_link_id': 'bound-link', 'custom_canvas_assignment_id': '1'}
    exchange(client, assignment_launch(client, params))
    assert assignment_launch(client, {**params, 'custom_canvas_assignment_id': '2'}).status_code == 409


def test_invalid_optional_metadata_does_not_prevent_draft_creation(client, configured_lti11):
    result = exchange(client, assignment_launch(client, {
        'resource_link_title': 'x' * 250,
        'custom_canvas_assignment_due_at': 'not-a-date',
        'custom_canvas_assignment_description': '$Canvas.assignment.description',
    }))
    with store.connection() as conn:
        item = assignment(conn, result['assignment_id'])
        assert len(item['title']) == 200
        assert item['due_at'] is None
        assert item['instructions'] == ''


def test_assignment_destination_is_bound_to_one_time_code_not_browser_query(client, configured_lti11):
    response = assignment_launch(client)
    code = parse_qs(urlsplit(response.headers['location']).query)['code'][0]
    result = client.post('/api/lti/exchange?assignment_id=' + str(uuid4()), json={'code': code}).json()
    assert result['assignment_id']
    assert result['assignment_id'] in result['redirect_path']


def test_canvas_chatbot_selection_survives_relaunch_and_opens_correct_student_engine(client, configured_lti11):
    params = {'user_id': str(uuid4()), 'context_id': str(uuid4()), 'resource_link_id': 'chosen-debate'}
    teacher = exchange(client, assignment_launch(client, params))
    aid = teacher['assignment_id']
    path = f'/api/platform/assignments/{aid}'
    headers = {'Authorization': 'Bearer ' + teacher['access_token']}
    saved = client.put(path, headers=headers, json={
        'course_id': teacher['course_id'], 'tool': 'debate', 'title': 'Discuss code reviews',
        'instructions': 'Defend your position.', 'audience': 'course',
        'config': {'scenario': 'Should teams require every change to receive a code review?', 'opening_prompt': 'Which position would you defend?'},
    })
    assert saved.status_code == 200, saved.text
    assert client.post(path + '/publish', headers=headers).status_code == 200
    reopened = exchange(client, assignment_launch(client, params))
    assert reopened['assignment_id'] == aid
    assert reopened['redirect_path'] == (
        f"/platform/professor/activities/{aid}?course={reopened['course_id']}"
    )
    assert client.get(path, headers=headers).json()['tool'] == 'debate'
    learner = exchange(client, assignment_launch(client, {**params, 'user_id': str(uuid4()), 'roles': 'Learner'}))
    student_headers = {'Authorization': 'Bearer ' + learner['access_token']}
    opened = client.post(path + '/start', headers=student_headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()['messages'][0]['content'] == 'Which position would you defend?'
