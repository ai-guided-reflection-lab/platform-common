"""Real OAuth signatures and PostgreSQL provisioning for Canvas LTI 1.1."""
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from fastapi import HTTPException
from oauthlib.oauth1 import Client, SIGNATURE_TYPE_BODY

from app import settings
from platform_app import lti11, store


@pytest.fixture
def configured_lti11(monkeypatch):
    values = {
        "LTI_CANVAS_ISSUER": "https://instructure.charlotte.edu",
        "LTI_PUBLIC_BASE_URL": "https://cluball.example",
        "LTI11_CONSUMER_KEY": "cluball-test-consumer",
        "LTI11_SHARED_SECRET": "test secret & unicode é",
        "LTI_CLIENT_ID": "", "LTI_DEPLOYMENT_ID": "", "LTI_TOOL_PRIVATE_KEY_B64": "",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def signed(values=None, *, key=None, secret=None, timestamp=None, nonce=None, url=None):
    params = {
        "lti_message_type": "basic-lti-launch-request", "lti_version": "LTI-1p0",
        "user_id": str(uuid4()), "context_id": str(uuid4()), "resource_link_id": "nav-1",
        "roles": "Instructor", "context_title": "Software Engineering",
        "context_label": "ITCS 3155", "lis_person_name_full": "Renée + A & B",
    }
    params.update(values or {})
    signer = Client(key or settings.LTI11_CONSUMER_KEY,
                    client_secret=secret or settings.LTI11_SHARED_SECRET,
                    signature_type=SIGNATURE_TYPE_BODY,
                    timestamp=str(timestamp or int(time.time())), nonce=nonce or uuid4().hex)
    _, headers, body = signer.sign(url or settings.LTI_PUBLIC_BASE_URL+lti11.LAUNCH_PATH,
                                  http_method="POST", body=urlencode(params),
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    return body, headers


def launch(client, values=None, **kwargs):
    body, headers = signed(values, **kwargs)
    return client.post(lti11.LAUNCH_PATH, content=body, headers=headers, follow_redirects=False)


def exchange(client, response):
    assert response.status_code == 303, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["lti"] == ["verified"]
    result = client.post("/api/lti/exchange", json={"code": query["code"][0]})
    assert result.status_code == 200, result.text
    assert client.post("/api/lti/exchange", json={"code": query["code"][0]}).status_code == 401
    return result.json()


def test_canvas_xml_and_independent_status(client, configured_lti11):
    result = client.get("/api/lti/canvas-config.xml")
    assert result.status_code == 200
    xml = ElementTree.fromstring(result.text)
    launch_url = xml.find("{http://www.imsglobal.org/xsd/imsbasiclti_v1p0}launch_url").text
    assert launch_url == "https://cluball.example/api/lti/1.1/launch"
    assert 'name="windowTarget">_blank' in result.text
    assert settings.LTI11_SHARED_SECRET not in result.text
    status = client.get("/api/lti/status").json()
    assert status["lti11_launch_configured"] is True
    assert status["launch_configured"] is False


def test_full_instructor_student_and_course_flow(client, configured_lti11):
    course = str(uuid4())
    teacher_id = str(uuid4())
    teacher = exchange(client, launch(client, {"context_id": course, "user_id": teacher_id}))
    assert teacher["user"]["authority_level"] == 1
    assert teacher["user"]["onboarding_complete"] is True
    assert teacher["access_token"]
    repeated = exchange(client, launch(client, {"context_id": course, "user_id": teacher_id}))
    assert repeated["user"]["user_id"] == teacher["user"]["user_id"]
    assert repeated["course_id"] == teacher["course_id"]
    assignment = str(uuid4())
    with store.connection() as conn:
        conn.execute("""INSERT INTO assignments_platform
            (id, course_id, creator_id, tool, title, audience, status, config, snapshot, published_at)
            VALUES (%s,%s,%s,'socratic','LTI test','course','published','{}','{}',NOW())""",
            (assignment, teacher["course_id"], teacher["user"]["user_id"]))
    student = exchange(client, launch(client, {"context_id": course, "roles": "Learner"}))
    assert student["course_id"] == teacher["course_id"]
    assert student["user"]["authority_level"] == 2
    with store.connection() as conn:
        membership = conn.execute("""SELECT course_role, status FROM course_memberships_platform
            WHERE course_id=%s AND user_id=%s""", (teacher["course_id"], student["user"]["user_id"])).fetchone()
        assert membership == {"course_role": "student", "status": "approved"}
        assert conn.execute("SELECT 1 FROM assignment_recipients_platform WHERE assignment_id=%s AND student_id=%s",
                            (assignment, student["user"]["user_id"])).fetchone()
    other = exchange(client, launch(client, {"user_id": teacher_id}))
    assert other["course_id"] != teacher["course_id"]
    with store.connection() as conn:
        assert not conn.execute("SELECT 1 FROM course_memberships_platform WHERE course_id=%s AND user_id=%s",
                                (other["course_id"], student["user"]["user_id"])).fetchone()


def test_student_first_rolls_back_account(client, configured_lti11):
    subject = str(uuid4())
    response = launch(client, {"roles": "Learner", "user_id": subject})
    assert response.status_code == 409
    with store.connection() as conn:
        assert not conn.execute("SELECT 1 FROM lti_identities_platform WHERE subject=%s", (subject,)).fetchone()


@pytest.mark.parametrize("kwargs", [
    {"secret": "wrong"}, {"key": "wrong"}, {"timestamp": 1},
    {"timestamp": 4102444800}, {"url": "https://attacker.example/api/lti/1.1/launch"},
])
def test_invalid_oauth(client, configured_lti11, kwargs):
    assert launch(client, **kwargs).status_code == 401


def test_tampering_duplicates_and_replay(client, configured_lti11):
    body, headers = signed()
    assert client.post(lti11.LAUNCH_PATH, content=body.replace("Instructor", "Learner"), headers=headers).status_code == 401
    assert client.post(lti11.LAUNCH_PATH, content=body+"&roles=Learner", headers=headers).status_code == 400
    assert client.post(lti11.LAUNCH_PATH, content=body, headers=headers, follow_redirects=False).status_code == 303
    assert client.post(lti11.LAUNCH_PATH, content=body, headers=headers).status_code == 401


@pytest.mark.parametrize("values, status", [
    ({"user_id": ""}, 422), ({"context_id": ""}, 422), ({"resource_link_id": ""}, 422),
    ({"lti_version": "1.3.0"}, 422), ({"roles": "Observer"}, 403),
    ({"roles": "NotAnInstructor"}, 403),
])
def test_invalid_launch_claims(client, configured_lti11, values, status):
    assert launch(client, values).status_code == status


def test_signed_query_and_proxy_headers(client, configured_lti11):
    body, headers = signed(url=settings.LTI_PUBLIC_BASE_URL+lti11.LAUNCH_PATH+"?label=a%2Bb")
    headers.update({"Host": "internal:8000", "X-Forwarded-Host": "attacker.example"})
    assert client.post(lti11.LAUNCH_PATH+"?label=a%2Bb", content=body, headers=headers, follow_redirects=False).status_code == 303
    assert client.post(lti11.LAUNCH_PATH+"?label=changed", content=body, headers=headers).status_code == 401


@pytest.mark.parametrize("name,value", [
    ("LTI11_SHARED_SECRET", ""), ("LTI11_CONSUMER_KEY", ""),
    ("LTI_PUBLIC_BASE_URL", "http://localhost"), ("LTI_PUBLIC_BASE_URL", "https://tool.example/path"),
    ("LTI_PUBLIC_BASE_URL", "https://tool.example:bad"), ("LTI_CANVAS_ISSUER", ""),
])
def test_unconfigured(client, configured_lti11, monkeypatch, name, value):
    monkeypatch.setattr(settings, name, value)
    assert client.get("/api/lti/canvas-config.xml").status_code == 503
    assert client.post(lti11.LAUNCH_PATH, data={}).status_code == 503
    assert client.get("/api/lti/status").json()["lti11_launch_configured"] is False


def test_atomic_nonce_and_expiration(configured_lti11):
    params = {"oauth_nonce": str(uuid4()), "oauth_timestamp": str(int(time.time()))}
    def consume(_):
        try:
            lti11._consume_nonce(params)
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, range(2))) == [200, 401]
    with store.connection() as conn:
        conn.execute("INSERT INTO lti11_nonces_platform VALUES ('expired-test-nonce', NOW()-INTERVAL '1 day')")
    lti11._consume_nonce({**params, "oauth_nonce": str(uuid4())})
    with store.connection() as conn:
        assert not conn.execute("SELECT 1 FROM lti11_nonces_platform WHERE nonce_hash='expired-test-nonce'").fetchone()


def test_registration_isolation(configured_lti11, monkeypatch):
    params = {"user_id": "1", "context_id": "1", "roles": "Instructor"}
    first = lti11._claims(params)
    monkeypatch.setattr(settings, "LTI11_CONSUMER_KEY", "another-registration")
    second = lti11._claims(params)
    assert first["iss"] != second["iss"]
    assert first["iss"] != settings.LTI_CANVAS_ISSUER


def test_rejects_wrong_encoding_and_large_body(client, configured_lti11):
    assert client.post(lti11.LAUNCH_PATH, json={}).status_code == 415
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    assert client.post(lti11.LAUNCH_PATH, content=b"\xff", headers=headers).status_code == 400
    assert client.post(lti11.LAUNCH_PATH, content="x"*65537, headers=headers).status_code == 413


@pytest.mark.parametrize("old,new", [
    ("oauth_version=1.0", "oauth_version=2.0"),
    ("oauth_signature_method=HMAC-SHA1", "oauth_signature_method=PLAINTEXT"),
])
def test_unsupported_oauth_parameters(client, configured_lti11, old, new):
    body, headers = signed()
    assert old in body
    assert client.post(lti11.LAUNCH_PATH, content=body.replace(old, new), headers=headers).status_code == 401


def test_concurrent_first_launches_share_account_and_course(configured_lti11):
    from platform_app import lti

    claims = lti11._claims({"user_id": str(uuid4()), "context_id": str(uuid4()), "roles": "Instructor"})
    def provision(_):
        return lti._provision_launch(claims, deployment_id="lti11")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(provision, range(2)))
    assert first[1] == second[1]
    assert first[0] != second[0]
