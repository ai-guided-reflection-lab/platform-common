import base64
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import settings
from platform_app import lti
from platform_app import store


@pytest.fixture
def configured_lti(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=lti.serialization.Encoding.PEM,
        format=lti.serialization.PrivateFormat.PKCS8,
        encryption_algorithm=lti.serialization.NoEncryption(),
    )
    values = {
        "LTI_CANVAS_ISSUER": "https://instructure.charlotte.edu",
        "LTI_CLIENT_ID": "canvas-client-123",
        "LTI_DEPLOYMENT_ID": "deployment-456",
        "LTI_PLATFORM_JWKS_URL": "https://sso.canvaslms.com/api/lti/security/jwks",
        "LTI_PUBLIC_BASE_URL": "https://cluball.example",
        "LTI_TOOL_PRIVATE_KEY_B64": base64.b64encode(pem).decode(),
        "LTI_TOOL_KEY_ID": "cluball-test-key",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return values


def start_login(client):
    response = client.get(
        "/api/lti/login",
        params={
            "iss": settings.LTI_CANVAS_ISSUER,
            "client_id": settings.LTI_CLIENT_ID,
            "login_hint": "canvas-login-hint",
            "lti_message_hint": "canvas-message-hint",
            "target_link_uri": f"{settings.LTI_PUBLIC_BASE_URL}/api/lti/launch",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["nonce"][0]
    assert query["redirect_uri"] == [
        f"{settings.LTI_PUBLIC_BASE_URL}/api/lti/launch"
    ]
    return query["state"][0], query["nonce"][0]


def launch_claims(subject, context_id, role):
    return {
        "iss": settings.LTI_CANVAS_ISSUER,
        "sub": subject,
        "email": f"{subject}@charlotte.edu",
        "name": subject.replace("-", " ").title(),
        lti.DEPLOYMENT_CLAIM: settings.LTI_DEPLOYMENT_ID,
        lti.MESSAGE_TYPE_CLAIM: "LtiResourceLinkRequest",
        lti.VERSION_CLAIM: "1.3.0",
        lti.ROLES_CLAIM: [
            f"http://purl.imsglobal.org/vocab/lis/v2/membership#{role}"
        ],
        lti.CONTEXT_CLAIM: {
            "id": context_id,
            "label": "ITCS 3155",
            "title": "Software Engineering",
        },
    }


def test_exposes_canvas_course_navigation_configuration(client, configured_lti):
    response = client.get("/api/lti/canvas-config")
    assert response.status_code == 200
    config = response.json()
    assert config["oidc_initiation_url"] == "https://cluball.example/api/lti/login"
    assert config["public_jwk_url"] == "https://cluball.example/api/lti/jwks"
    assert config["extensions"][0]["settings"]["placements"] == [
        {
            "placement": "course_navigation",
            "message_type": "LtiResourceLinkRequest",
            "target_link_uri": "https://cluball.example/api/lti/launch",
            "text": "ClubALL",
            "enabled": True,
        }
    ]

    jwks = client.get("/api/lti/jwks").json()
    assert jwks["keys"][0]["kid"] == "cluball-test-key"
    assert jwks["keys"][0]["kty"] == "RSA"


def test_instructor_launch_creates_course_and_one_time_session(
    client,
    configured_lti,
    monkeypatch,
):
    state, _nonce = start_login(client)
    claims = launch_claims("canvas-instructor", "canvas-course-101", "Instructor")
    monkeypatch.setattr(lti, "_verify_launch_token", lambda token, expected: claims)

    launch = client.post(
        "/api/lti/launch",
        data={"state": state, "id_token": "signed-canvas-token"},
        follow_redirects=False,
    )
    assert launch.status_code == 303
    redirect = parse_qs(urlparse(launch.headers["location"]).query)
    assert redirect["lti"] == ["verified"]
    assert redirect["course"][0]

    exchange = client.post(
        "/api/lti/exchange",
        json={"code": redirect["code"][0]},
    )
    assert exchange.status_code == 200
    body = exchange.json()
    assert body["course_id"] == redirect["course"][0]
    assert body["user"]["authority_level"] == 1
    assert body["user"]["onboarding_complete"] is True
    assert body["access_token"]

    assignment_id = str(uuid4())
    with store.connection() as conn:
        conn.execute(
            """
            INSERT INTO assignments_platform (
                id, course_id, creator_id, tool, title, audience, status,
                config, snapshot, published_at
            )
            VALUES (%s, %s, %s, 'socratic', 'LTI assignment', 'course',
                    'published', '{}'::jsonb, '{}'::jsonb, NOW())
            """,
            (assignment_id, body["course_id"], body["user"]["user_id"]),
        )

    student_state, _student_nonce = start_login(client)
    claims = launch_claims("canvas-student-after-instructor", "canvas-course-101", "Learner")
    student_launch = client.post(
        "/api/lti/launch",
        data={"state": student_state, "id_token": "signed-student-token"},
        follow_redirects=False,
    )
    assert student_launch.status_code == 303
    student_redirect = parse_qs(urlparse(student_launch.headers["location"]).query)
    student_exchange = client.post(
        "/api/lti/exchange",
        json={"code": student_redirect["code"][0]},
    )
    assert student_exchange.status_code == 200
    student = student_exchange.json()
    assert student["course_id"] == body["course_id"]
    assert student["user"]["authority_level"] == 2
    with store.connection() as conn:
        membership = conn.execute(
            """
            SELECT course_role, status
            FROM course_memberships_platform
            WHERE course_id = %s AND user_id = %s
            """,
            (body["course_id"], student["user"]["user_id"]),
        ).fetchone()
        recipient = conn.execute(
            """
            SELECT 1
            FROM assignment_recipients_platform
            WHERE assignment_id = %s AND student_id = %s
            """,
            (assignment_id, student["user"]["user_id"]),
        ).fetchone()
    assert membership == {"course_role": "student", "status": "approved"}
    assert recipient is not None

    repeated = client.post(
        "/api/lti/exchange",
        json={"code": redirect["code"][0]},
    )
    assert repeated.status_code == 401


def test_student_cannot_create_course_before_instructor_launch(
    client,
    configured_lti,
    monkeypatch,
):
    state, _nonce = start_login(client)
    claims = launch_claims("canvas-student", "new-student-course", "Learner")
    monkeypatch.setattr(lti, "_verify_launch_token", lambda token, expected: claims)

    response = client.post(
        "/api/lti/launch",
        data={"state": state, "id_token": "signed-canvas-token"},
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "instructor must launch" in response.json()["detail"].lower()


def test_rejects_untrusted_issuer_and_replayed_state(client, configured_lti, monkeypatch):
    bad_issuer = client.get(
        "/api/lti/login",
        params={
            "iss": "https://attacker.example",
            "client_id": settings.LTI_CLIENT_ID,
            "login_hint": "hint",
        },
        follow_redirects=False,
    )
    assert bad_issuer.status_code == 400

    state, _nonce = start_login(client)
    claims = launch_claims("replay-instructor", "replay-course", "Instructor")
    monkeypatch.setattr(lti, "_verify_launch_token", lambda token, expected: claims)
    first = client.post(
        "/api/lti/launch",
        data={"state": state, "id_token": "signed-canvas-token"},
        follow_redirects=False,
    )
    assert first.status_code == 303
    replay = client.post(
        "/api/lti/launch",
        data={"state": state, "id_token": "signed-canvas-token"},
        follow_redirects=False,
    )
    assert replay.status_code == 401


def test_launch_verification_rejects_signature_nonce_and_deployment(
    configured_lti,
    monkeypatch,
):
    class SigningKey:
        key = object()

    class JWKClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setattr(lti.jwt, "PyJWKClient", JWKClient)
    expected = {
        "nonce": "expected-nonce",
        "issuer": settings.LTI_CANVAS_ISSUER,
        "client_id": settings.LTI_CLIENT_ID,
    }
    claims = launch_claims("verified-user", "verified-course", "Learner")
    claims["nonce"] = "wrong-nonce"
    monkeypatch.setattr(lti.jwt, "decode", lambda *args, **kwargs: claims)
    with pytest.raises(lti.HTTPException, match="nonce"):
        lti._verify_launch_token("token", expected)

    claims["nonce"] = "expected-nonce"
    claims[lti.DEPLOYMENT_CLAIM] = "untrusted-deployment"
    with pytest.raises(lti.HTTPException, match="deployment"):
        lti._verify_launch_token("token", expected)

    def invalid_signature(*args, **kwargs):
        raise jwt.InvalidSignatureError()

    monkeypatch.setattr(lti.jwt, "decode", invalid_signature)
    with pytest.raises(lti.HTTPException, match="signature"):
        lti._verify_launch_token("token", expected)
