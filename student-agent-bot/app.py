"""Simple SE tutor chatbot — local web UI."""

import json
import os
import hmac
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT.parent / "env", override=False)

from firecrawl_fetch import fetch_url_preview  # noqa: E402
from adaptive_assessor import assess_response  # noqa: E402
from topic_generator import generate_topic_draft  # noqa: E402
from models import PROVIDERS  # noqa: E402
from personalities import DEFAULT_PERSONALITY, list_personalities  # noqa: E402
from student import simulate_student_reply  # noqa: E402
from topics import (  # noqa: E402
    TopicValidationError,
    delete_custom_topic,
    get_topic,
    import_topic_json,
    list_topics,
    list_topics_detailed,
    save_custom_topic,
)
from tutor import Session, create_session, end_session, navigate_session, render_adaptive_action, set_practice_scenario, tutor_reply  # noqa: E402

app = FastAPI(title="SE Tutor Chat")
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_PATH = Path(__file__).resolve().parent / "data" / "topics" / "topic.template.json"

from session_store import SessionStore
from topic_store import validate_topic

sessions = SessionStore()


@app.middleware("http")
async def service_auth(request: Request, call_next):
    secret = os.getenv("PLATFORM_SERVICE_TOKEN", "")
    internal = request.url.path.startswith("/internal/")
    if (secret and request.url.path != "/health") or internal:
        if not secret or not hmac.compare_digest(request.headers.get("x-platform-service", ""), secret):
            return JSONResponse({"detail": "Platform service authentication required."}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


def saved_public(session):
    sessions[session.session_id] = session
    return session.to_public()


class StartRequest(BaseModel):
    topic_id: str
    provider: str = Field(pattern=r"^(groq|openai)$")
    personality: str = DEFAULT_PERSONALITY
    session_id: str | None = None
    topic_snapshot: dict | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SessionRequest(BaseModel):
    session_id: str


class PersonalityRequest(BaseModel):
    session_id: str
    personality: str


class NavigateRequest(BaseModel):
    session_id: str
    phase: str


class ScenarioRequest(BaseModel):
    session_id: str
    scenario: str


class ResourceInput(BaseModel):
    title: str
    url: str


class PracticeStageInput(BaseModel):
    label: str
    focus: str


class TopicCreateRequest(BaseModel):
    id: str | None = None
    name: str
    resource: ResourceInput
    alt_resource: ResourceInput
    practice_label: str
    practice_prompt: str
    practice_stages: list[PracticeStageInput]
    practice_options: list[str] = []
    check_questions: list[str] = []
    final_example: str


class FetchUrlRequest(BaseModel):
    url: str


class TopicGenerateRequest(BaseModel):
    name: str
    provider: str = Field(default="groq", pattern=r"^(groq|openai)$")


def _topic_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TopicValidationError):
        return HTTPException(400, str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc))
    return HTTPException(500, str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def get_config():
    return {
        "topics": list_topics(),
        "providers": [
            {"id": key, "label": value["label"], "env_key": value["env_key"]}
            for key, value in PROVIDERS.items()
        ],
        "personalities": list_personalities(),
        "default_personality": DEFAULT_PERSONALITY,
    }


@app.post("/api/session/start")
def start_session(body: StartRequest):
    if body.provider not in PROVIDERS:
        raise HTTPException(400, "Invalid provider")
    try:
        validate_topic(body.topic_snapshot) if body.topic_snapshot else get_topic(body.topic_id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown topic: {body.topic_id}") from exc
    env_key = PROVIDERS[body.provider]["env_key"]
    if not os.getenv(env_key):
        raise HTTPException(
            400,
            f"Missing {env_key} in env file. Add it to ../env and restart.",
        )

    session_id = body.session_id or str(uuid.uuid4())
    existing = sessions.get(session_id)
    if existing:
        return existing.to_public()
    session = create_session(session_id, body.topic_id, body.provider, body.personality, body.topic_snapshot)
    sessions[session_id] = session
    return saved_public(session)


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return saved_public(session)


@app.post("/api/chat")
def chat(body: ChatRequest):
    session = sessions.get(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.ended:
        raise HTTPException(400, "Session has ended. Reset or resume from a saved transcript.")

    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty")

    try:
        tutor_reply(session, message)
    except Exception as exc:
        raise HTTPException(502, f"Tutor error: {exc}") from exc

    return saved_public(session)


@app.post("/api/simulate-student")
def simulate(body: SessionRequest):
    session = sessions.get(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.ended:
        raise HTTPException(400, "Session has ended. Reset to start again.")

    try:
        student_message = simulate_student_reply(session)
        tutor_reply(session, student_message)
    except Exception as exc:
        raise HTTPException(502, f"Simulation error: {exc}") from exc

    return {
        **saved_public(session),
        "simulated_student_message": student_message,
    }


@app.patch("/api/session/personality")
def update_personality(body: PersonalityRequest):
    session = sessions.get(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    session.personality = body.personality
    return saved_public(session)


@app.post("/api/session/navigate")
def change_phase(body: NavigateRequest):
    session = sessions.get(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        navigate_session(session, body.phase)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Tutor error: {exc}") from exc
    return saved_public(session)


@app.post("/api/session/scenario")
def choose_scenario(body: ScenarioRequest):
    session = sessions.get(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        set_practice_scenario(session, body.scenario)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Tutor error: {exc}") from exc
    return saved_public(session)


@app.post("/api/session/end")
def close_session(body: SessionRequest):
    session = sessions.get(body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    end_session(session)
    return saved_public(session)


@app.post("/api/session/reset")
def reset_session(body: SessionRequest):
    sessions.pop(body.session_id, None)
    return {"ok": True}


@app.get("/api/topics/manage")
def manage_topics_list():
    return {"topics": list_topics_detailed()}


@app.get("/api/topics/template")
def download_template():
    if not TEMPLATE_PATH.exists():
        raise HTTPException(404, "Template not found")
    return FileResponse(TEMPLATE_PATH, filename="topic.template.json")


@app.post("/api/topics/generate")
def generate_topic(body: TopicGenerateRequest):
    if not os.getenv("FIRECRAWL_API_KEY"):
        raise HTTPException(400, "FIRECRAWL_API_KEY required in env for topic generation")
    env_key = PROVIDERS[body.provider]["env_key"]
    if not os.getenv(env_key):
        raise HTTPException(400, f"Missing {env_key} for LLM generation")

    try:
        draft = generate_topic_draft(body.name, body.provider)
        return {"ok": True, "draft": draft}
    except (TopicValidationError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Generation failed: {exc}") from exc


@app.post("/api/topics")
def create_topic(body: TopicCreateRequest):
    try:
        saved = save_custom_topic(body.model_dump())
        return {"ok": True, "topic": {"id": saved["id"], "name": saved["name"]}, "topics": list_topics()}
    except (TopicValidationError, ValueError) as exc:
        raise _topic_error(exc) from exc


@app.post("/api/topics/upload")
async def upload_topic(file: UploadFile = File(...)):
    try:
        raw = json.loads((await file.read()).decode("utf-8"))
        saved = import_topic_json(raw)
        return {"ok": True, "count": len(saved), "topics": list_topics()}
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid JSON file") from exc
    except (TopicValidationError, ValueError) as exc:
        raise _topic_error(exc) from exc


@app.delete("/api/topics/{topic_id}")
def remove_topic(topic_id: str):
    try:
        delete_custom_topic(topic_id)
        return {"ok": True, "topics": list_topics()}
    except (TopicValidationError, KeyError) as exc:
        raise _topic_error(exc) from exc


@app.post("/api/topics/fetch-url")
def fetch_reading_url(body: FetchUrlRequest):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL must start with http:// or https://")
    try:
        return fetch_url_preview(url)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch URL: {exc}") from exc


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PlatformAction(BaseModel):
    session_id: str
    request_id: str
    action: str
    value: str


class AdaptiveStart(BaseModel):
    session_id: str
    provider: str = Field(pattern=r"^(groq|openai)$")
    plan_title: str
    decision: dict
    objective: dict
    assessment_prompt: str


class AdaptiveAssess(BaseModel):
    provider: str = Field(pattern=r"^(groq|openai)$")
    objective: dict
    assessment: dict
    student_response: str


class AdaptiveRender(BaseModel):
    session_id: str
    request_id: str
    student_message: str
    provider: str = Field(pattern=r"^(groq|openai)$")
    plan_title: str
    decision: dict
    objective: dict
    assessment_prompt: str
    assessment_result: dict | None = None
    rag_context: list[dict] = Field(default_factory=list)


def _adaptive_topic(title: str) -> dict:
    placeholder = {"title": "Professor-approved course material", "url": "https://example.invalid/course-material"}
    return {
        "id": "adaptive_oop", "name": title, "resource": placeholder,
        "alt_resource": placeholder, "practice_label": "adaptive practice",
        "practice_prompt": "Follow the application-selected adaptive action.",
        "practice_stages": [{"label": "adaptive", "focus": "Current objective"}],
        "practice_options": [], "check_questions": [], "final_example": "",
    }


@app.post("/internal/platform/adaptive/start")
def adaptive_start(body: AdaptiveStart):
    existing = sessions.get(body.session_id)
    if existing:
        return existing.to_public()
    session = Session(
        session_id=body.session_id,
        topic_id="adaptive_oop",
        provider=body.provider,
        phase="checking",
        topic_snapshot=_adaptive_topic(body.plan_title),
        unlocked_phases=["checking"],
    )
    render_adaptive_action(session, body.decision, body.objective, body.assessment_prompt)
    sessions[body.session_id] = session
    return session.to_public()


@app.post("/internal/platform/adaptive/assess")
def adaptive_assess(body: AdaptiveAssess):
    try:
        return assess_response(body.provider, body.objective, body.assessment, body.student_response)
    except Exception as exc:
        raise HTTPException(502, f"Assessment failed: {exc}") from exc


@app.post("/internal/platform/adaptive/render")
def adaptive_render(body: AdaptiveRender):
    def operation(session):
        render_adaptive_action(
            session, body.decision, body.objective, body.assessment_prompt,
            student_message=body.student_message,
            assessment_result=body.assessment_result,
            rag_context=body.rag_context,
        )
    try:
        return sessions.perform(body.session_id, body.request_id, operation)
    except KeyError:
        raise HTTPException(404, "Session not found")


@app.post("/internal/platform/action")
def platform_action(body: PlatformAction):
    def operation(session):
        if body.action == "message":
            tutor_reply(session, body.value)
        elif body.action == "navigate":
            navigate_session(session, body.value)
        elif body.action == "scenario":
            if session.phase != "practice":
                raise ValueError("Reach practice before choosing a scenario")
            set_practice_scenario(session, body.value)
        else:
            raise ValueError("Unknown action")
    try:
        return sessions.perform(body.session_id, body.request_id, operation)
    except KeyError:
        raise HTTPException(404, "Session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
