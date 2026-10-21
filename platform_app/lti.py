"""Shared Canvas LTI 1.1 account provisioning and browser session exchange."""
from __future__ import annotations

import hashlib
import secrets
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import auth, db, settings
from platform_app import store, lti_assignments


ROLES_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/roles"
CONTEXT_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/context"

router = APIRouter(prefix="/api/lti", tags=["lti"])


class LTIExchangeRequest(BaseModel):
    code: str = Field(min_length=20, max_length=200)


@router.get("/status")
def lti_status():
    from platform_app.lti11 import enabled as lti11_enabled

    return {
        "lti11_launch_configured": lti11_enabled(),
        "assignment_auto_creation_enabled": settings.LTI_AUTO_CREATE_ASSIGNMENTS,
    }


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


def _provision_launch(
    claims: dict[str, object], *, deployment_id: str,
) -> tuple[str, str]:
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
        # Serialize first-time identity/course creation across workers. Row locks
        # alone cannot lock an identity or course that does not exist yet.
        for lock_key in (f"lti-user:{issuer}:{subject}", f"lti-course:{issuer}:{deployment_id}:{context_id}"):
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
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
            (issuer, deployment_id, context_id),
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
            suffix = hashlib.sha256(f"{issuer}:{deployment_id}:{context_id}".encode()).hexdigest()[:6].upper()
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
                (issuer, deployment_id, context_id, course_id),
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
        assignment_id = lti_assignments.provision(
            conn, claims, issuer=issuer, deployment_id=deployment_id,
            context_id=context_id, course_id=course_id, user_id=user_id, role=role,
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
                (code_hash, user_id, course_id, assignment_id, launch_role, expires_at)
            VALUES (%s, %s, %s, %s, %s, NOW() + INTERVAL '5 minutes')
            """,
            (hashlib.sha256(code.encode()).hexdigest(), user_id, course_id, assignment_id, role),
        )
    return code, course_id


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
            RETURNING user_id::text, course_id::text, assignment_id::text, launch_role
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
    role = row["launch_role"] or ("instructor" if int(account["authority_level"]) <= 1 else "student")
    assignment_id = row["assignment_id"]
    course_query = urlencode({"course": str(row["course_id"])})
    if assignment_id:
        with store.connection() as conn:
            assignment = conn.execute(
                'SELECT tool FROM assignments_platform WHERE id=%s AND course_id=%s',
                (assignment_id, row["course_id"]),
            ).fetchone()
        if not assignment:
            raise HTTPException(409, "The linked assignment is no longer available in this course.")
        redirect_path = (
            f'/platform/professor/activities/{assignment_id}?{course_query}'
            if role == 'instructor' else f'/platform/student/assignments/{assignment_id}'
        )
    else:
        redirect_path = (
            f'/platform/professor/activities/new?{course_query}'
            if role == 'instructor'
            else f'/platform/student?{course_query}'
        )
    return {
        "user": account,
        "access_token": access_token,
        "expires_in_seconds": expires_in_seconds,
        "course_id": str(row["course_id"]),
        "assignment_id": assignment_id,
        "redirect_path": redirect_path,
    }
