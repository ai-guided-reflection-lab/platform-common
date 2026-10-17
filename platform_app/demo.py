"""Self-service demo profiles. Never grant roles to existing application users."""
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr, field_validator

from app import db, settings
from platform_app import store
from platform_app.routes import user

router = APIRouter(prefix="/api/platform/demo", tags=["demo"])


def enabled():
    # A deployment must opt in and isolate all learning data from live courses.
    return os.getenv("PLATFORM_DEMO_MODE", "false").lower() == "true" and all(
        name.startswith("demo_") for name in (
            settings.PLATFORM_DB_SCHEMA, settings.SOCRATIC_DB_SCHEMA,
            settings.SHARED_RAG_DB_SCHEMA,
            os.getenv("SELF_DIRECTED_LEARNING_DB_SCHEMA", ""),
            os.getenv("REFLECTIONS_DB_SCHEMA", ""),
        )
    )


def require_demo():
    if not enabled():
        raise HTTPException(404, "Not found.")


class DemoEntry(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a username.")
        return value


class DemoRole(BaseModel):
    role: str = Field(pattern="^(student|professor)$")


def session_for(identity):
    from app.main import _auth_response
    response = _auth_response(db.get_user_by_id(str(identity)))
    return {**response.model_dump(mode="json"), "demo_mode": True}


@router.get("/config")
def config():
    return {"enabled": enabled()}


@router.post("/enter", dependencies=[Depends(require_demo)])
def enter(body: DemoEntry):
    username = body.username.casefold()
    password = body.password.get_secret_value()
    with store.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("demo:" + username,))
        profiles = conn.execute("SELECT * FROM demo_profiles_platform WHERE username=%s", (username,)).fetchall()
        profile = next((p for p in profiles if db._password_matches(password, p["password_salt"], p["password_hash"])), None)
        if profile is None:
            profile_id, professor_id, student_id = uuid4(), uuid4(), uuid4()
            salt, hashed = db._hash_password(password)
            for identity, role, level in ((professor_id, "professor", 1), (student_id, "student", 2)):
                internal_name = f"demo-{profile_id.hex}-{role}"
                conn.execute("""INSERT INTO users_platform
                    (id,username,email,display_name,password_salt,password_hash,authority_level,onboarding_completed_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,now())""",
                    (identity, internal_name, internal_name + "@example.invalid", body.username, salt, hashed, level))
            conn.execute("""INSERT INTO demo_profiles_platform
                (id,username,password_salt,password_hash,professor_id,student_id)
                VALUES (%s,%s,%s,%s,%s,%s)""", (profile_id, username, salt, hashed, professor_id, student_id))
        else:
            professor_id = profile["professor_id"]
    return session_for(professor_id)


@router.post("/role", dependencies=[Depends(require_demo)])
def switch_role(body: DemoRole, account=Depends(user)):
    with store.connection() as conn:
        profile = conn.execute("""SELECT professor_id,student_id FROM demo_profiles_platform
            WHERE professor_id=%s OR student_id=%s""", (account["user_id"], account["user_id"])).fetchone()
    if not profile:
        raise HTTPException(403, "Open a demo profile before switching roles.")
    return session_for(profile[body.role + "_id"])
