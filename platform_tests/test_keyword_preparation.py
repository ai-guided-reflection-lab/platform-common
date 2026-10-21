from platform_app import engines, store
from test_assignments import draft
from test_learning_objectives import material


def ready_assignment(client, roster, words=None):
    _, document_id, chunk_id = material(roster)
    item, body = draft(client, roster, config={'keywords': words or ['code review'],
        'optional_keywords': ['unit testing'], 'document_ids': [document_id]})
    return item, body, chunk_id, f"/api/platform/assignments/{item['id']}"


def test_confirm_is_private_persistent_and_publish_reuses_prepared_materials(client, roster, monkeypatch):
    item, body, chunk, path = ready_assignment(client, roster)
    teacher = roster['headers']['prof']
    assert client.post(path+'/publish', headers=teacher).status_code == 409
    confirmed = client.post(path+'/keywords/confirm', headers=teacher)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['ready'] is True
    assert confirmed.json()['keywords'] == ['code review']
    assert confirmed.json()['passage_count'] == 1
    assert 'snapshot' not in confirmed.json() and 'chunks' not in confirmed.json()
    detail = client.get(path, headers=teacher).json()
    assert detail['status'] == 'draft'
    assert detail['keyword_preparation']['ready'] is True
    assert client.get(path, headers=roster['headers']['student']).status_code == 404
    with store.connection() as conn:
        cached = conn.execute('SELECT prepared_snapshot FROM assignment_keyword_preparations_platform WHERE assignment_id=%s', (item['id'],)).fetchone()['prepared_snapshot']
    assert cached['approved_keywords'] == ['code review']
    assert [source['chunk_id'] for source in cached['chunks']] == [chunk]
    def forbidden(*args, **kwargs): raise AssertionError('Rebuilt an already prepared snapshot')
    monkeypatch.setattr(engines, 'publish_snapshot', forbidden)
    assert client.post(path+'/keywords/confirm', headers=teacher).status_code == 200
    published = client.post(path+'/publish', headers=teacher)
    assert published.status_code == 200, published.text
    student = client.get(path, headers=roster['headers']['student']).json()
    assert 'keyword_preparation' not in student and 'config' not in student and 'snapshot' not in student
    assert client.post(path+'/keywords/confirm', headers=teacher).status_code == 409


def test_changed_approved_keywords_require_confirmation_but_optional_changes_do_not(client, roster):
    item, body, chunk, path = ready_assignment(client, roster)
    teacher = roster['headers']['prof']
    assert client.post(path+'/keywords/confirm', headers=teacher).status_code == 200
    body['config']['optional_keywords'] = ['debugging']
    saved = client.put(path, headers=teacher, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['keyword_preparation']['ready'] is True
    body['config']['keywords'] = ['consistency']
    changed = client.put(path, headers=teacher, json=body)
    assert changed.json()['keyword_preparation']['ready'] is False
    assert changed.json()['keyword_preparation']['reason'] == 'keywords_changed'
    assert client.post(path+'/publish', headers=teacher).status_code == 409
    assert client.post(path+'/keywords/confirm', headers=teacher).json()['keywords'] == ['consistency']
    assert client.post(path+'/publish', headers=teacher).status_code == 200


def test_dismissed_keyword_is_saved_with_draft_without_changing_approved_keywords(client, roster):
    item, body, _chunk, path = ready_assignment(client, roster)
    body['config']['dismissed_keywords'] = ['Unneeded topic']
    saved = client.put(path, headers=roster['headers']['prof'], json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['config']['dismissed_keywords'] == ['Unneeded topic']
    assert saved.json()['config']['keywords'] == ['code review']
    reloaded = client.get(path, headers=roster['headers']['prof'])
    assert reloaded.json()['config']['dismissed_keywords'] == ['Unneeded topic']


def test_changed_materials_invalidate_preparation(client, roster):
    item, body, chunk, path = ready_assignment(client, roster)
    teacher = roster['headers']['prof']
    assert client.post(path+'/keywords/confirm', headers=teacher).status_code == 200
    with store.connection() as conn:
        conn.execute('UPDATE chunks SET chunk_text=%s WHERE id=%s', ('Changed notes about code review.', chunk))
    state = client.get(path, headers=teacher).json()['keyword_preparation']
    assert state['ready'] is False and state['reason'] == 'materials_changed'
    assert client.post(path+'/publish', headers=teacher).status_code == 409
    assert client.post(path+'/keywords/confirm', headers=teacher).status_code == 200
    assert client.post(path+'/publish', headers=teacher).status_code == 200


def test_confirm_requires_managing_instructor_and_nonempty_keywords(client, roster):
    item, body, chunk, path = ready_assignment(client, roster)
    for account in ('student', 'other_prof'):
        assert client.post(path+'/keywords/confirm', headers=roster['headers'][account]).status_code == 403
    body['config']['keywords'] = []
    assert client.put(path, headers=roster['headers']['prof'], json=body).status_code == 200
    assert client.post(path+'/keywords/confirm', headers=roster['headers']['prof']).status_code == 422
    with store.connection() as conn:
        assert not conn.execute('SELECT 1 FROM assignment_keyword_preparations_platform WHERE assignment_id=%s', (item['id'],)).fetchone()


def test_material_change_during_preparation_does_not_save_a_partial_result(client, roster, monkeypatch):
    item, body, chunk, path = ready_assignment(client, roster)
    original = engines.publish_snapshot
    def changing(assignment):
        snapshot = original(assignment)
        with store.connection() as conn:
            conn.execute('UPDATE chunks SET chunk_text=%s WHERE id=%s', ('Concurrent edit.', chunk))
        return snapshot
    monkeypatch.setattr(engines, 'publish_snapshot', changing)
    result = client.post(path+'/keywords/confirm', headers=roster['headers']['prof'])
    assert result.status_code == 409, result.text
    with store.connection() as conn:
        assert not conn.execute('SELECT 1 FROM assignment_keyword_preparations_platform WHERE assignment_id=%s', (item['id'],)).fetchone()
