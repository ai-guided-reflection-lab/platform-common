import pytest


@pytest.mark.parametrize("query", [
    "lti=verified&code=one-use-code&course=test-course",
    "github=verified&code=one-use-code",
    "github=school_email_required",
    "manage=1",
])
def test_root_auth_handoffs_keep_the_existing_exchange_page(client, query):
    response = client.get('/?' + query, follow_redirects=False)
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'location' not in response.headers


def test_plain_root_opens_replacement_workspace(client):
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/platform/'
