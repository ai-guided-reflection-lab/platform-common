"""Canvas LTI 1.3 course-navigation launch and account provisioning."""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import auth, db, settings
from platform_app import store


DEPLOYMENT_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
MESSAGE_TYPE_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/message_type"
VERSION_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/version"
ROLES_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/roles"
CONTEXT_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/context"

router = APIRouter(prefix="/api/lti", tags=["lti"])


class LTIExchangeRequest(BaseModel):
    code: str = Field(min_length=20, max_length=200)


def _valid_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username


def _tool_configuration_ready() -> bool:
    return (
        all(
            (
                settings.LTI_PUBLIC_BASE_URL,
                settings.LTI_TOOL_PRIVATE_KEY_B64,
                settings.LTI_TOOL_KEY_ID,
            )
        )
        and _valid_https_url(settings.LTI_PUBLIC_BASE_URL)
    )


def _enabled() -> bool:
    return (
        _tool_configuration_ready()
        and all(
            (
                settings.LTI_CANVAS_ISSUER,
                settings.LTI_CLIENT_ID,
                settings.LTI_DEPLOYMENT_ID,
                settings.LTI_PLATFORM_JWKS_URL,
            )
        )
        and _valid_https_url(settings.LTI_CANVAS_ISSUER)
        and _valid_https_url(settings.LTI_PLATFORM_JWKS_URL)
    )


def _require_tool_configuration() -> None:
    if not _tool_configuration_ready():
        raise HTTPException(
            status_code=503,
            detail="Canvas LTI tool configuration is not ready on this server.",
        )


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail="Canvas LTI is not configured on this server.",
        )


def _url(path: str) -> str:
    return f"{settings.LTI_PUBLIC_BASE_URL}{path}"


def _private_key():
    try:
        key_bytes = base64.b64decode(
            settings.LTI_TOOL_PRIVATE_KEY_B64,
            validate=True,
        )
        return serialization.load_pem_private_key(key_bytes, password=None)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail="The Canvas LTI signing key is invalid.",
        ) from error


def _public_jwk() -> dict[str, object]:
    try:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            _private_key().public_key(),
            as_dict=True,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail="The Canvas LTI signing key must be an RSA private key.",
        ) from error
    return {
        **jwk,
        "kid": settings.LTI_TOOL_KEY_ID,
        "use": "sig",
        "alg": "RS256",
    }


@router.get("/status")
def lti_status():
    return {
        "tool_configuration_ready": _tool_configuration_ready(),
        "launch_configured": _enabled(),
    }


@router.get("/jwks")
def lti_jwks():
    _require_tool_configuration()
    return {"keys": [_public_jwk()]}


@router.get("/canvas-config")
def canvas_configuration():
    _require_tool_configuration()
    launch_url = _url("/api/lti/launch")
    return {
        "title": "ClubALL Learning Platform",
        "description": "Course-grounded Socratic, reflection, and tutoring assignments.",
        "oidc_initiation_url": _url("/api/lti/login"),
        "target_link_uri": launch_url,
        "public_jwk_url": _url("/api/lti/jwks"),
        "scopes": [],
        "extensions": [
            {
                "domain": urlsplit(settings.LTI_PUBLIC_BASE_URL).netloc,
                "tool_id": "cluball",
                "platform": "canvas.instructure.com",
                "privacy_level": "public",
                "settings": {
                    "text": "ClubALL",
                    "custom_fields": {
                        "canvas_course_id": "$Canvas.course.id",
                        "canvas_user_id": "$Canvas.user.id",
                    },
                    "placements": [
                        {
                            "placement": "course_navigation",
                            "message_type": "LtiResourceLinkRequest",
                            "target_link_uri": launch_url,
                            "text": "ClubALL",
                            "enabled": True,
                        }
                    ],
                },
            }
        ],
    }


def _request_parameter(request: Request, form: dict[str, object], name: str) -> str:
    return str(form.get(name) or request.query_params.get(name) or "").strip()


async def _start_login(request: Request) -> RedirectResponse:
    _require_enabled()
    form = dict(await request.form()) if request.method == "POST" else {}
    issuer = _request_parameter(request, form, "iss").rstrip("/")
    client_id = _request_parameter(request, form, "client_id")
    login_hint = _request_parameter(request, form, "login_hint")
    message_hint = _request_parameter(request, form, "lti_message_hint")
    target_link_uri = _request_parameter(request, form, "target_link_uri")

    if issuer != settings.LTI_CANVAS_ISSUER:
        raise HTTPException(status_code=400, detail="Canvas LTI issuer is not trusted.")
    if client_id and client_id != settings.LTI_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Canvas LTI client ID is not trusted.")
    if not login_hint:
        raise HTTPException(status_code=422, detail="Canvas did not provide a login hint.")
    if target_link_uri and target_link_uri != _url("/api/lti/launch"):
        raise HTTPException(status_code=400, detail="Canvas requested an invalid launch URL.")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    with store.connection() as conn:
        conn.execute(
            "DELETE FROM lti_launch_states_platform WHERE expires_at < NOW() - INTERVAL '1 day'"
        )
        conn.execute(
            """
            INSERT INTO lti_launch_states_platform
                (state_hash, nonce, issuer, client_id, expires_at)
            VALUES (%s, %s, %s, %s, NOW() + INTERVAL '10 minutes')
            """,
            (state_hash, nonce, issuer, settings.LTI_CLIENT_ID),
        )

    query = {
        "scope": "openid",
        "response_type": "id_token",
        "response_mode": "form_post",
        "prompt": "none",
        "client_id": settings.LTI_CLIENT_ID,
        "redirect_uri": _url("/api/lti/launch"),
        "login_hint": login_hint,
        "state": state,
        "nonce": nonce,
    }
    if message_hint:
        query["lti_message_hint"] = message_hint
    return RedirectResponse(
        f"{settings.LTI_CANVAS_ISSUER}/api/lti/authorize_redirect?{urlencode(query)}",
        status_code=302,
    )


@router.get("/login")
async def lti_login_get(request: Request):
    return await _start_login(request)


@router.post("/login")
async def lti_login_post(request: Request):
    return await _start_login(request)


def _consume_state(state: str) -> dict[str, str]:
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    with store.connection() as conn:
        row = conn.execute(
            """
            UPDATE lti_launch_states_platform
            SET used_at = NOW()
            WHERE state_hash = %s
              AND used_at IS NULL
              AND expires_at > NOW()
            RETURNING nonce, issuer, client_id
            """,
            (state_hash,),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=401,
            detail="Canvas LTI launch state is invalid, expired, or already used.",
        )
    return {
        "nonce": str(row["nonce"]),
        "issuer": str(row["issuer"]),
        "client_id": str(row["client_id"]),
    }


def _verify_launch_token(id_token: str, expected: dict[str, str]) -> dict[str, object]:
    try:
        signing_key = jwt.PyJWKClient(
            settings.LTI_PLATFORM_JWKS_URL,
            cache_keys=True,
        ).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected["client_id"],
            issuer=expected["issuer"],
            options={"require": ["exp", "iat", "iss", "aud", "nonce", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=401,
            detail="Canvas LTI launch signature could not be verified.",
        ) from error

    if not secrets.compare_digest(str(claims.get("nonce") or ""), expected["nonce"]):
        raise HTTPException(status_code=401, detail="Canvas LTI launch nonce is invalid.")
    if claims.get(DEPLOYMENT_CLAIM) != settings.LTI_DEPLOYMENT_ID:
        raise HTTPException(status_code=403, detail="Canvas LTI deployment is not trusted.")
    if claims.get(MESSAGE_TYPE_CLAIM) != "LtiResourceLinkRequest":
        raise HTTPException(status_code=422, detail="Canvas sent an unsupported LTI message.")
    if claims.get(VERSION_CLAIM) != "1.3.0":
        raise HTTPException(status_code=422, detail="Canvas sent an unsupported LTI version.")
    return claims


def _lti_role(claims: dict[str, object]) -> str:
    claim_roles = claims.get(ROLES_CLAIM)
    if not isinstance(claim_roles, list):
        raise HTTPException(status_code=403, detail="Canvas did not provide a supported course role.")
    roles = {
        str(role).rsplit("#", 1)[-1].rsplit("/", 1)[-1].lower()
        for role in claim_roles
    }
    if roles & {"instructor", "administrator", "teachingassistant", "contentdeveloper"}:
        return "instructor"
    if roles & {"learner", "student"}:
        return "student"
    raise HTTPException(status_code=403, detail="Canvas did not provide a supported course role.")


def _unique_username(conn, desired: str) -> str:
    base = "".join(
        character
        for character in desired.strip().lower().replace(" ", ".")
        if character.isalnum() or character in {"_", "-", "."}
    )
    base = (base.strip(".") or "canvas.user")[:60]
    candidate = base
    suffix = 1
    while conn.execute(
        "SELECT 1 FROM users_platform WHERE lower(username) = lower(%s)",
        (candidate,),
    ).fetchone():
        suffix += 1
        candidate = f"{base[:70]}-{suffix}"
    return candidate


def _provision_launch(claims: dict[str, object]) -> tuple[str, str]:
    issuer = str(claims["iss"]).rstrip("/")
    subject = str(claims["sub"])
    role = _lti_role(claims)
    context = claims.get(CONTEXT_CLAIM)
    if not isinstance(context, dict) or not str(context.get("id") or "").strip():
        raise HTTPException(status_code=422, detail="Canvas launch is missing its course context.")

    context_id = str(context["id"])
    email = str(claims.get("email") or "").strip().lower()
    display_name = str(claims.get("name") or claims.get("given_name") or "Canvas user").strip()
    authority_level = 1 if role == "instructor" else 2

    with store.connection() as conn:
        identity = conn.execute(
            """
            SELECT user_id::text
            FROM lti_identities_platform
            WHERE issuer = %s AND subject = %s
            FOR UPDATE
            """,
            (issuer, subject),
        ).fetchone()
        user_id = str(identity["user_id"]) if identity else ""

        if not user_id and email:
            existing = conn.execute(
                "SELECT id::text FROM users_platform WHERE lower(email) = %s FOR UPDATE",
                (email,),
            ).fetchone()
            user_id = str(existing["id"]) if existing else ""
            if user_id:
                conflicting_identity = conn.execute(
                    """
                    SELECT subject
                    FROM lti_identities_platform
                    WHERE issuer = %s AND user_id = %s AND subject <> %s
                    """,
                    (issuer, user_id, subject),
                ).fetchone()
                if conflicting_identity:
                    raise HTTPException(
                        status_code=409,
                        detail="This email is already linked to another Canvas identity.",
                    )

        if not user_id:
            user_id = str(uuid4())
            username = _unique_username(
                conn,
                str(claims.get("preferred_username") or email.partition("@")[0] or display_name),
            )
            internal_email = email or f"lti-{hashlib.sha256(f'{issuer}:{subject}'.encode()).hexdigest()[:24]}@users.invalid"
            salt, password_hash = db._hash_password(secrets.token_urlsafe(48))
            conn.execute(
                """
                INSERT INTO users_platform (
                    id, username, display_name, email, password_salt, password_hash,
                    auth_provider, authority_level, onboarding_completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'lti', %s, NOW())
                """,
                (
                    user_id,
                    username,
                    display_name,
                    internal_email,
                    salt,
                    password_hash,
                    authority_level,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE users_platform
                SET display_name = COALESCE(NULLIF(%s, ''), display_name),
                    authority_level = CASE
                        WHEN %s = 1 THEN LEAST(authority_level, 1)
                        ELSE authority_level
                    END,
                    onboarding_completed_at = COALESCE(onboarding_completed_at, NOW())
                WHERE id = %s
                """,
                (display_name, authority_level, user_id),
            )

        conn.execute(
            """
            INSERT INTO lti_identities_platform (issuer, subject, user_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (issuer, subject) DO UPDATE
            SET user_id = EXCLUDED.user_id, updated_at = NOW()
            """,
            (issuer, subject, user_id),
        )

        linked_course = conn.execute(
            """
            SELECT course_id::text
            FROM lti_course_links_platform
            WHERE issuer = %s AND deployment_id = %s AND context_id = %s
            FOR UPDATE
            """,
            (issuer, settings.LTI_DEPLOYMENT_ID, context_id),
        ).fetchone()
        course_id = str(linked_course["course_id"]) if linked_course else ""

        if not course_id:
            if role != "instructor":
                raise HTTPException(
                    status_code=409,
                    detail="An instructor must launch ClubALL from this Canvas course before students can enter.",
                )
            course_id = str(uuid4())
            label = " ".join(str(context.get("label") or "CANVAS").upper().split())[:32]
            suffix = hashlib.sha256(context_id.encode()).hexdigest()[:6].upper()
            course_code = f"{label}-{suffix}"[:40]
            title = " ".join(str(context.get("title") or label).split())[:160]
            conn.execute(
                """
                INSERT INTO courses_platform
                    (id, course_code, title, description, instructor_id, is_discoverable)
                VALUES (%s, %s, %s, %s, %s, FALSE)
                """,
                (course_id, course_code, title, "Created from a verified Canvas LTI launch.", user_id),
            )
            conn.execute(
                """
                INSERT INTO lti_course_links_platform
                    (issuer, deployment_id, context_id, course_id)
                VALUES (%s, %s, %s, %s)
                """,
                (issuer, settings.LTI_DEPLOYMENT_ID, context_id, course_id),
            )

        conn.execute(
            """
            INSERT INTO course_memberships_platform
                (id, course_id, user_id, course_role, status, reviewed_at, reviewed_by)
            VALUES (%s, %s, %s, %s, 'approved', NOW(), %s)
            ON CONFLICT (course_id, user_id) DO UPDATE
            SET course_role = CASE
                    WHEN EXCLUDED.course_role = 'instructor' THEN 'instructor'
                    ELSE course_memberships_platform.course_role
                END,
                status = 'approved',
                reviewed_at = NOW(),
                reviewed_by = EXCLUDED.reviewed_by,
                rejection_reason = NULL
            """,
            (str(uuid4()), course_id, user_id, role, user_id),
        )
        if role == "student":
            conn.execute(
                """
                INSERT INTO assignment_recipients_platform (assignment_id, student_id)
                SELECT id, %s
                FROM assignments_platform
                WHERE course_id = %s AND audience = 'course' AND status = 'published'
                ON CONFLICT DO NOTHING
                """,
                (user_id, course_id),
            )

        code = secrets.token_urlsafe(32)
        conn.execute(
            "DELETE FROM lti_login_codes_platform WHERE expires_at < NOW() - INTERVAL '1 day'"
        )
        conn.execute(
            """
            INSERT INTO lti_login_codes_platform
                (code_hash, user_id, course_id, expires_at)
            VALUES (%s, %s, %s, NOW() + INTERVAL '5 minutes')
            """,
            (hashlib.sha256(code.encode()).hexdigest(), user_id, course_id),
        )
    return code, course_id


@router.post("/launch")
async def lti_launch(request: Request):
    _require_enabled()
    form = await request.form()
    state = str(form.get("state") or "").strip()
    id_token = str(form.get("id_token") or "").strip()
    if not state or not id_token:
        raise HTTPException(status_code=422, detail="Canvas launch is missing state or ID token.")
    expected = _consume_state(state)
    claims = _verify_launch_token(id_token, expected)
    code, course_id = _provision_launch(claims)
    return RedirectResponse(
        f"/?{urlencode({'lti': 'verified', 'code': code, 'course': course_id})}",
        status_code=303,
    )


@router.post("/exchange")
def lti_exchange(payload: LTIExchangeRequest):
    code_hash = hashlib.sha256(payload.code.encode()).hexdigest()
    with store.connection() as conn:
        row = conn.execute(
            """
            UPDATE lti_login_codes_platform
            SET used_at = NOW()
            WHERE code_hash = %s
              AND used_at IS NULL
              AND expires_at > NOW()
            RETURNING user_id::text, course_id::text
            """,
            (code_hash,),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=401,
            detail="Canvas sign-in expired or was already used.",
        )
    account = db.get_user_by_id(str(row["user_id"]))
    if not account:
        raise HTTPException(status_code=401, detail="Canvas account was not found.")
    access_token, expires_in_seconds = auth.issue_session(str(row["user_id"]))
    return {
        "user": account,
        "access_token": access_token,
        "expires_in_seconds": expires_in_seconds,
        "course_id": str(row["course_id"]),
    }
