import json
import hashlib
import secrets
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb

from app import auth, db, settings
from platform_app import canvas_lms, engines, store
from platform_app.schemas import (
    AssignmentInput,
    CanvasCourseRequest,
    CanvasCredentials,
    CanvasImportRequest,
    GenerateSubtopicsInput,
    MessageInput,
    SelfDirectedStudyInput, SelfDirectedQuizInput, SelfDirectedMessageInput,
    SelfDirectedTaskInput, SelfDirectedLearningTurn,
)

router = APIRouter(prefix="/api/platform", tags=["platform"])


def user(request: Request):
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Please sign in.")
    uid = auth.verify_session(token)["sub"]
    account = db.get_user_by_id(uid)
    if not account:
        raise HTTPException(401, "Account not found.")
    if not account.get("onboarding_complete"):
        raise HTTPException(403, "Complete account setup first.")
    if settings.REQUIRE_GITHUB_ACCOUNT and not db.user_has_github(uid):
        raise HTTPException(403, "Connect your GitHub account first.")
    return account


def professor(account=Depends(user)):
    if int(account["authority_level"]) > 1:
        raise HTTPException(403, "Professor access is required.")
    return account


def manage_course(course_id, account):
    if not db.user_manages_course(str(course_id), str(account["user_id"])):
        raise HTTPException(403, "You do not manage this course.")


def get_assignment(conn, assignment_id, account, manage=False, lock=False):
    item = conn.execute("SELECT * FROM assignments_platform WHERE id=%s" + (" FOR UPDATE" if lock else ""), (assignment_id,)).fetchone()
    if not item or item["tool"] not in {"socratic", "reflections", "debate", "self-directed-learning"}:
        raise HTTPException(404, "Assignment not found.")
    if manage:
        manage_course(item["course_id"], account)
    else:
        # Enrollment revocation takes effect immediately, even for existing attempts.
        allowed = conn.execute("""SELECT 1 FROM assignment_recipients_platform r JOIN course_memberships_platform m
            ON m.user_id=r.student_id AND m.course_id=%s
            WHERE r.assignment_id=%s AND r.student_id=%s AND m.status='approved' AND m.course_role='student'""",
            (item["course_id"], assignment_id, account["user_id"])).fetchone()
        if item["status"] != "published" or not allowed:
            raise HTTPException(404, "Assignment not found or no longer available.")
    return item


def public_assignment(item, manage=False):
    result = {k: v for k, v in item.items() if k not in ("snapshot", "config")}
    if manage:
        result["config"] = item["config"]
    else:
        cfg = (item.get("snapshot") or {}).get("config", item["config"])
        # Never send historical student data, model answers, or instructor notes to students.
        if item["tool"] == "reflections":
            result["student_config"] = {k: cfg[k] for k in ("module_type", "milestone_prompt")}
        elif item["tool"] == "debate":
            result["student_config"] = {k: cfg[k] for k in ("scenario", "minimum_messages")}
        elif item["tool"] == "socratic":
            result["student_config"] = {"minimum_messages": cfg["minimum_messages"]}
    return result


def public_attempt(attempt):
    return {k: v for k, v in attempt.items() if k != "processed_requests"} if attempt else None


def recipients(conn, assignment_id, body):
    conn.execute("DELETE FROM assignment_recipients_platform WHERE assignment_id=%s", (assignment_id,))
    if body.audience == "selected":
        for sid in set(body.recipient_ids):
            if not conn.execute("SELECT 1 FROM course_memberships_platform WHERE course_id=%s AND user_id=%s AND status='approved' AND course_role='student'",
                                (body.course_id, sid)).fetchone():
                raise HTTPException(422, "Every selected student must be enrolled in this course.")
            conn.execute("INSERT INTO assignment_recipients_platform VALUES (%s, %s)", (assignment_id, sid))


@router.get("/tools")
def tools(account=Depends(user)):
    return [
        {"id": "debate", "name": "Debate", "description": "Build and defend your argument."},
        {"id": "socratic", "name": "Socratic Chat", "description": "Explore questions grounded in your course materials."},
        {"id": "reflections", "name": "Reflections", "description": "Guide students through topics or milestone reflections."},
        {"id": "self-directed-learning", "name": "Self-Directed Learning", "description": "Study resources and follow your adaptive learning path."},
    ]






@router.post("/generate-subtopics")
def generate_subtopics(body: GenerateSubtopicsInput, account=Depends(professor)):
    return engines.call("reflections", "POST", "/api/modules/subtopics/generate", json=body.model_dump())


def canvas_result(operation):
    try:
        return operation()
    except canvas_lms.CanvasAPIError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/integrations/canvas/courses")
def canvas_courses(body: CanvasCredentials, _account=Depends(professor)):
    return canvas_result(lambda: canvas_lms.list_courses(body.access_token.get_secret_value()))


@router.post("/integrations/canvas/assignments")
def canvas_assignments(body: CanvasCourseRequest, _account=Depends(professor)):
    return canvas_result(
        lambda: canvas_lms.list_assignments(body.course_id, body.access_token.get_secret_value())
    )


@router.post("/integrations/canvas/import", status_code=201)
def import_canvas_assignment(body: CanvasImportRequest, account=Depends(professor)):
    manage_course(body.platform_course_id, account)
    canvas_assignment = canvas_result(
        lambda: canvas_lms.get_assignment(
            body.course_id,
            body.assignment_id,
            body.access_token.get_secret_value(),
        )
    )
    source = canvas_assignment.get("html_url")
    source_note = f"\n\nCanvas source: {source}" if source else ""
    description_limit = max(0, 10_000 - len(source_note))
    instructions = f"{canvas_assignment['description'][:description_limit]}{source_note}".strip()
    config = {}
    if body.tool == "socratic":
        config = {
            "prompt": (
                "Help the learner reason through this Canvas assignment using only the "
                f"published course materials: {canvas_assignment['name']}"
            ),
            "minimum_messages": 1,
        }
    return create_assignment(
        AssignmentInput(
            course_id=body.platform_course_id,
            tool=body.tool,
            title=canvas_assignment["name"][:200],
            instructions=instructions,
            due_at=canvas_assignment.get("due_at"),
            audience="course",
            config=config,
        ),
        account,
    )


@router.get("/assignments")
def assignments(account=Depends(user)):
    is_prof = int(account["authority_level"]) <= 1
    with store.connection() as conn:
        if is_prof:
            rows = conn.execute("""SELECT a.*, c.title AS course_title, c.course_code,
                (SELECT count(*) FROM assignment_recipients_platform WHERE assignment_id=a.id) AS recipient_count,
                (SELECT count(*) FROM assignment_attempts_platform WHERE assignment_id=a.id AND status='completed') AS completed_count
                FROM assignments_platform a JOIN courses_platform c ON c.id=a.course_id
                WHERE c.instructor_id=%s ORDER BY a.created_at DESC""", (account["user_id"],)).fetchall()
        else:
            rows = conn.execute("""SELECT a.*, c.title AS course_title, c.course_code, coalesce(t.status, 'not_started') AS progress
                FROM assignments_platform a JOIN courses_platform c ON c.id=a.course_id
                JOIN assignment_recipients_platform r ON r.assignment_id=a.id AND r.student_id=%s
                JOIN course_memberships_platform m ON m.course_id=a.course_id AND m.user_id=r.student_id AND m.status='approved'
                LEFT JOIN assignment_attempts_platform t ON t.assignment_id=a.id AND t.student_id=r.student_id
                WHERE a.status='published' AND m.course_role='student' ORDER BY a.due_at NULLS LAST, a.created_at DESC""", (account["user_id"],)).fetchall()
        result = [public_assignment(row, is_prof) for row in rows if row["tool"] in {"socratic", "reflections", "debate", "self-directed-learning"}]
    if not is_prof:
        try:
            lessons = self_directed_assignments(account)
            by_id = {str(item["id"]): item for item in lessons}
            for item in result:
                if item["tool"] == "self-directed-learning" and str(item["id"]) in by_id:
                    lesson = by_id[str(item["id"])]
                    item["progress"] = lesson.get("attempt_status") or "not_started"
            known = {str(item["id"]) for item in result}
            result.extend(self_directed_assignment_summary(item) for item in lessons if str(item["id"]) not in known)
        except HTTPException as exc:
            if exc.status_code not in {502, 503}:
                raise
    return result


@router.post("/assignments", status_code=201)
def create_assignment(body: AssignmentInput, account=Depends(professor)):
    manage_course(body.course_id, account)
    assignment_id = uuid4()
    with store.connection() as conn:
        row = conn.execute("""INSERT INTO assignments_platform(id, course_id, creator_id, tool, title, instructions, due_at, audience, config)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", (assignment_id, body.course_id, account["user_id"], body.tool,
            body.title, body.instructions, body.due_at, body.audience, Jsonb(body.config))).fetchone()
        recipients(conn, assignment_id, body)
    return public_assignment(row, True)


@router.get("/assignments/{assignment_id}")
def assignment_detail(assignment_id: UUID, account=Depends(user)):
    is_prof = int(account["authority_level"]) <= 1
    with store.connection() as conn:
        item = get_assignment(conn, assignment_id, account, manage=is_prof)
        result = public_assignment(item, is_prof)
        if is_prof:
            result["recipient_ids"] = [r["student_id"] for r in conn.execute("SELECT student_id FROM assignment_recipients_platform WHERE assignment_id=%s", (assignment_id,))]
            result["students"] = conn.execute("""SELECT u.display_name, u.username, u.id AS student_id,
                coalesce(t.status, 'not_started') AS progress, t.completed_at, t.result
                FROM assignment_recipients_platform r JOIN users_platform u ON u.id=r.student_id
                LEFT JOIN assignment_attempts_platform t ON t.assignment_id=r.assignment_id AND t.student_id=r.student_id
                WHERE r.assignment_id=%s ORDER BY u.username""", (assignment_id,)).fetchall()
        if is_prof and item["tool"] == "self-directed-learning" and item["status"] == "published":
            from platform_app.shared_rag import pipeline
            result["students"] = pipeline("GET", f"/internal/platform/lessons/{assignment_id}/progress")
        return result


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: UUID, body: AssignmentInput, account=Depends(professor)):
    manage_course(body.course_id, account)
    with store.connection() as conn:
        item = get_assignment(conn, assignment_id, account, manage=True, lock=True)
        if item["status"] != "draft":
            raise HTTPException(409, "Published assignments are frozen. Duplicate the assignment to make changes.")
        if item["tool"] != body.tool:
            raise HTTPException(422, "An assignment's tool cannot be changed.")
        row = conn.execute("""UPDATE assignments_platform SET course_id=%s,title=%s,instructions=%s,due_at=%s,audience=%s,config=%s,updated_at=now()
            WHERE id=%s RETURNING *""", (body.course_id, body.title, body.instructions, body.due_at, body.audience, Jsonb(body.config), assignment_id)).fetchone()
        recipients(conn, assignment_id, body)
        return public_assignment(row, True)


@router.post("/assignments/{assignment_id}/publish")
def publish(assignment_id: UUID, account=Depends(professor)):
    with store.connection() as conn:
        item = get_assignment(conn, assignment_id, account, manage=True, lock=True)
        if item["status"] == "published":
            return public_assignment(item, True)
        if item["status"] != "draft":
            raise HTTPException(409, "Archived assignments cannot be published.")
        if item["audience"] == "course":
            conn.execute("""INSERT INTO assignment_recipients_platform SELECT %s, user_id FROM course_memberships_platform
                WHERE course_id=%s AND status='approved' AND course_role='student' ON CONFLICT DO NOTHING""", (assignment_id, item["course_id"]))
        # Recheck selected recipients in case enrollment changed after saving the draft.
        invalid = conn.execute("""SELECT 1 FROM assignment_recipients_platform r WHERE assignment_id=%s AND NOT EXISTS
            (SELECT 1 FROM course_memberships_platform m WHERE m.course_id=%s AND m.user_id=r.student_id AND m.status='approved' AND m.course_role='student')""",
            (assignment_id, item["course_id"])).fetchone()
        if invalid:
            raise HTTPException(422, "A selected student is no longer enrolled. Update the draft's recipients.")
        try:
            if item["tool"] == "self-directed-learning":
                from platform_app.workspace import publish_sdl
                publish_sdl(conn, item, account)
            snapshot = engines.publish_snapshot(item)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = conn.execute("UPDATE assignments_platform SET status='published', snapshot=%s, published_at=now(),updated_at=now() WHERE id=%s RETURNING *",
                           (Jsonb(snapshot), assignment_id)).fetchone()
        return public_assignment(row, True)


@router.post("/assignments/{assignment_id}/archive")
def archive(assignment_id: UUID, account=Depends(professor)):
    with store.connection() as conn:
        get_assignment(conn, assignment_id, account, manage=True, lock=True)
        conn.execute("UPDATE assignments_platform SET status='archived', updated_at=now() WHERE id=%s", (assignment_id,))
    return {"status": "archived"}


@router.post("/assignments/{assignment_id}/duplicate", status_code=201)
def duplicate(assignment_id: UUID, account=Depends(professor)):
    with store.connection() as conn:
        item = get_assignment(conn, assignment_id, account, manage=True)
    return create_assignment(AssignmentInput(course_id=item["course_id"], tool=item["tool"], title=item["title"][:190] + " (copy)",
                            instructions=item["instructions"], config=item["config"]), account)


@router.get("/assignments/{assignment_id}/attempt")
def attempt_detail(assignment_id: UUID, account=Depends(user)):
    with store.connection() as conn:
        get_assignment(conn, assignment_id, account)
        return public_attempt(conn.execute("SELECT * FROM assignment_attempts_platform WHERE assignment_id=%s AND student_id=%s", (assignment_id, account["user_id"])).fetchone())


@router.post("/assignments/{assignment_id}/start")
def start(assignment_id: UUID, account=Depends(user)):
    with store.locked_attempt(assignment_id, account["user_id"]) as (conn, attempt):
        assignment = get_assignment(conn, assignment_id, account)
        if attempt:
            return public_attempt(attempt)
        # Deterministic identity lets engine starts recover from a lost gateway response.
        aid = uuid5(NAMESPACE_URL, f"cluball:{assignment_id}:{account['user_id']}")
        attempt = conn.execute("INSERT INTO assignment_attempts_platform(id,assignment_id,student_id) VALUES (%s,%s,%s) RETURNING *", (aid, assignment_id, account["user_id"])).fetchone()
        state = engines.start(assignment, attempt)
        attempt["messages"] = state.pop("messages", [])
        attempt["engine_state"] = state
        store.save_attempt(conn, attempt)
        return public_attempt(attempt)


def apply_state(attempt, state, content=None):
    if "messages" in state:
        attempt["messages"] = state.pop("messages")
    else:
        if content:
            attempt["messages"].append({"role": "user", "content": content})
        if state.get("reply"):
            attempt["messages"].append({"role": "assistant", "content": state["reply"]})
    if state.pop("completed", False) or state.get("ended"):
        attempt["status"] = "completed"
        attempt["result"] = state.get("result", {"phase": state.get("phase")})
    attempt["engine_state"].update(state)


@router.post("/assignments/{assignment_id}/messages")
def message(assignment_id: UUID, body: MessageInput, account=Depends(user)):
    with store.locked_attempt(assignment_id, account["user_id"]) as (conn, attempt):
        assignment = get_assignment(conn, assignment_id, account)
        if not attempt:
            raise HTTPException(409, "Start the assignment first.")
        rid = str(body.request_id)
        if rid in attempt["processed_requests"]:
            return public_attempt(attempt)
        if attempt["status"] == "completed":
            raise HTTPException(409, "This assignment is already completed.")
        state = engines.message(assignment, attempt, body.message, rid)
        apply_state(attempt, state, body.message)
        attempt["processed_requests"].append(rid)
        store.save_attempt(conn, attempt)
        return public_attempt(attempt)




@router.post("/assignments/{assignment_id}/complete")
def complete(assignment_id: UUID, account=Depends(user)):
    with store.locked_attempt(assignment_id, account["user_id"]) as (conn, attempt):
        assignment = get_assignment(conn, assignment_id, account)
        if not attempt:
            raise HTTPException(409, "Start the assignment first.")
        if attempt["status"] == "completed":
            return public_attempt(attempt)
        result = engines.complete(assignment, attempt)
        attempt["result"] = result
        attempt["status"] = "completed"
        store.save_attempt(conn, attempt)
        return public_attempt(attempt)


def student(request: Request, account=Depends(user)):
    if int(account["authority_level"]) <= 1:
        raise HTTPException(403, "Student access is required.")
    assignment_id = request.path_params.get("assignment_id")
    if assignment_id:
        with store.connection() as conn:
            linked = conn.execute("SELECT id FROM assignments_platform WHERE id::text=%s", (assignment_id,)).fetchone()
            if linked:
                get_assignment(conn, linked["id"], account)
    return account



def self_directed_assignment_summary(item: dict) -> dict:
    return {
        "id": item["id"],
        "tool": "self-directed-learning",
        "title": item["title"],
        "instructions": item.get("instructions", ""),
        "course_code": "Self-Directed Learning",
        "course_title": "Self-Directed Learning",
        "due_at": None,
        "progress": item.get("attempt_status") or "not_started",
        "source": "self_directed_learning",
    }



def self_directed_identity(account) -> str:
    return engines.resolve_self_directed_student(account)



@router.get("/self-directed/assignments")
def self_directed_assignments(account=Depends(student)):
    student_id = self_directed_identity(account)
    lessons = engines.self_directed_call(student_id, "GET", "/api/student/assignments")
    with store.connection() as conn:
        linked = {str(r["id"]) for r in conn.execute("SELECT id FROM assignments_platform WHERE tool='self-directed-learning'").fetchall()}
        allowed = {str(r["id"]) for r in conn.execute("""SELECT a.id FROM assignments_platform a
            JOIN assignment_recipients_platform r ON r.assignment_id=a.id
            JOIN course_memberships_platform m ON m.course_id=a.course_id AND m.user_id=r.student_id
            WHERE a.tool='self-directed-learning' AND a.status='published' AND r.student_id=%s
            AND m.status='approved' AND m.course_role='student'""", (account["user_id"],)).fetchall()}
    return [lesson for lesson in lessons if str(lesson["id"]) not in linked or str(lesson["id"]) in allowed]



@router.post("/self-directed/assignments/{assignment_id}/learning-turn")
def self_directed_learning_turn(assignment_id: str, body: SelfDirectedLearningTurn, account=Depends(student)):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(student_id, "POST", f"/api/student/assignments/{assignment_id}/learning-turn", json=body.model_dump())



@router.get("/self-directed/assignments/{assignment_id}")
def self_directed_assignment(assignment_id: str, account=Depends(student)):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id, "GET", f"/api/student/assignments/{assignment_id}"
    )



@router.get("/self-directed/assignments/{assignment_id}/attempt")
def self_directed_attempt(assignment_id: str, account=Depends(student)):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id, "GET", f"/api/student/assignments/{assignment_id}/attempt"
    )



@router.post("/self-directed/assignments/{assignment_id}/start")
def start_self_directed_assignment(assignment_id: str, account=Depends(student)):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id, "POST", f"/api/student/assignments/{assignment_id}/start"
    )



@router.post("/self-directed/assignments/{assignment_id}/study-complete")
def complete_self_directed_study(
    assignment_id: str, body: SelfDirectedStudyInput, account=Depends(student)
):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id,
        "POST",
        f"/api/student/assignments/{assignment_id}/study-complete",
        json=body.model_dump(),
    )



@router.post("/self-directed/assignments/{assignment_id}/quiz")
def submit_self_directed_quiz(
    assignment_id: str, body: SelfDirectedQuizInput, account=Depends(student)
):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id,
        "POST",
        f"/api/student/assignments/{assignment_id}/quiz",
        json=body.model_dump(),
    )



@router.post("/self-directed/assignments/{assignment_id}/messages")
def send_self_directed_message(
    assignment_id: str, body: SelfDirectedMessageInput, account=Depends(student)
):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id,
        "POST",
        f"/api/student/assignments/{assignment_id}/messages",
        json=body.model_dump(),
    )



@router.post("/self-directed/assignments/{assignment_id}/restart")
def restart_self_directed_assignment(assignment_id: str, account=Depends(student)):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id, "POST", f"/api/student/assignments/{assignment_id}/restart"
    )



@router.post("/self-directed/assignments/{assignment_id}/submit-task")
def submit_self_directed_task(
    assignment_id: str, body: SelfDirectedTaskInput, account=Depends(student)
):
    student_id = self_directed_identity(account)
    return engines.self_directed_call(
        student_id,
        "POST",
        f"/api/student/assignments/{assignment_id}/submit-task",
        json=body.model_dump(),
    )
