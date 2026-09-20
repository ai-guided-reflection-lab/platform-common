import json
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb

from app import auth, db, settings
from platform_app import adaptive_runtime, engines, store
from platform_app.adaptive import oop_learning_plan
from platform_app.schemas import AssignmentInput, MessageInput, ActionInput, GenerateTopicInput, GenerateSubtopicsInput

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
    item = conn.execute("SELECT * FROM platform_assignments WHERE id=%s" + (" FOR UPDATE" if lock else ""), (assignment_id,)).fetchone()
    if not item:
        raise HTTPException(404, "Assignment not found.")
    if manage:
        manage_course(item["course_id"], account)
    else:
        # Enrollment revocation takes effect immediately, even for existing attempts.
        allowed = conn.execute("""SELECT 1 FROM platform_recipients r JOIN course_memberships m
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
        elif item["tool"] == "socratic":
            result["student_config"] = {"minimum_messages": cfg["minimum_messages"]}
        else:
            if cfg.get("learning_plan"):
                plan = cfg["learning_plan"]
                result["student_config"] = {
                    "topic_name": plan["title"],
                    "learning_plan": plan,
                    "resources": plan.get("approved_resources", []),
                }
            else:
                topic = cfg["topic"]
                result["student_config"] = {"topic_name": topic["name"], "resources": [topic["resource"], topic["alt_resource"]]}
    return result


def public_attempt(attempt):
    return {k: v for k, v in attempt.items() if k != "processed_requests"} if attempt else None


def recipients(conn, assignment_id, body):
    conn.execute("DELETE FROM platform_recipients WHERE assignment_id=%s", (assignment_id,))
    if body.audience == "selected":
        for sid in set(body.recipient_ids):
            if not conn.execute("SELECT 1 FROM course_memberships WHERE course_id=%s AND user_id=%s AND status='approved' AND course_role='student'",
                                (body.course_id, sid)).fetchone():
                raise HTTPException(422, "Every selected student must be enrolled in this course.")
            conn.execute("INSERT INTO platform_recipients VALUES (%s, %s)", (assignment_id, sid))


@router.get("/tools")
def tools(account=Depends(user)):
    return [
        {"id": "socratic", "name": "Socratic Chat", "description": "Explore questions grounded in your course materials."},
        {"id": "reflections", "name": "Reflections", "description": "Guide students through topics or milestone reflections."},
        {"id": "student-agent", "name": "Student Agent Bot", "description": "Read, check understanding, and practice with a tutor."},
    ]


@router.get("/topic-templates")
def templates(account=Depends(professor)):
    return engines.topic_templates()


@router.get("/adaptive-plans")
def adaptive_plans(account=Depends(professor)):
    return [oop_learning_plan().model_dump(mode="json")]


@router.post("/generate-topic")
def generate_topic(body: GenerateTopicInput, account=Depends(professor)):
    return engines.call("student-agent", "POST", "/api/topics/generate", json=body.model_dump())


@router.post("/generate-subtopics")
def generate_subtopics(body: GenerateSubtopicsInput, account=Depends(professor)):
    return engines.call("reflections", "POST", "/api/modules/subtopics/generate", json=body.model_dump())


@router.get("/assignments")
def assignments(account=Depends(user)):
    is_prof = int(account["authority_level"]) <= 1
    with store.connection() as conn:
        if is_prof:
            rows = conn.execute("""SELECT a.*, c.title AS course_title, c.course_code,
                (SELECT count(*) FROM platform_recipients WHERE assignment_id=a.id) AS recipient_count,
                (SELECT count(*) FROM platform_attempts WHERE assignment_id=a.id AND status='completed') AS completed_count
                FROM platform_assignments a JOIN courses c ON c.id=a.course_id
                WHERE c.instructor_id=%s ORDER BY a.created_at DESC""", (account["user_id"],)).fetchall()
        else:
            rows = conn.execute("""SELECT a.*, c.title AS course_title, c.course_code, coalesce(t.status, 'not_started') AS progress
                FROM platform_assignments a JOIN courses c ON c.id=a.course_id
                JOIN platform_recipients r ON r.assignment_id=a.id AND r.student_id=%s
                JOIN course_memberships m ON m.course_id=a.course_id AND m.user_id=r.student_id AND m.status='approved'
                LEFT JOIN platform_attempts t ON t.assignment_id=a.id AND t.student_id=r.student_id
                WHERE a.status='published' AND m.course_role='student' ORDER BY a.due_at NULLS LAST, a.created_at DESC""", (account["user_id"],)).fetchall()
        return [public_assignment(row, is_prof) for row in rows]


@router.post("/assignments", status_code=201)
def create_assignment(body: AssignmentInput, account=Depends(professor)):
    manage_course(body.course_id, account)
    assignment_id = uuid4()
    with store.connection() as conn:
        row = conn.execute("""INSERT INTO platform_assignments(id, course_id, creator_id, tool, title, instructions, due_at, audience, config)
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
            result["recipient_ids"] = [r["student_id"] for r in conn.execute("SELECT student_id FROM platform_recipients WHERE assignment_id=%s", (assignment_id,))]
            result["students"] = conn.execute("""SELECT u.display_name, u.username, u.id AS student_id,
                coalesce(t.status, 'not_started') AS progress, t.completed_at, t.result
                FROM platform_recipients r JOIN users u ON u.id=r.student_id
                LEFT JOIN platform_attempts t ON t.assignment_id=r.assignment_id AND t.student_id=r.student_id
                WHERE r.assignment_id=%s ORDER BY u.username""", (assignment_id,)).fetchall()
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
        row = conn.execute("""UPDATE platform_assignments SET course_id=%s,title=%s,instructions=%s,due_at=%s,audience=%s,config=%s,updated_at=now()
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
            conn.execute("""INSERT INTO platform_recipients SELECT %s, user_id FROM course_memberships
                WHERE course_id=%s AND status='approved' AND course_role='student' ON CONFLICT DO NOTHING""", (assignment_id, item["course_id"]))
        count = conn.execute("SELECT count(*) AS n FROM platform_recipients WHERE assignment_id=%s", (assignment_id,)).fetchone()["n"]
        if not count:
            raise HTTPException(422, "Enroll at least one student before publishing.")
        # Recheck selected recipients in case enrollment changed after saving the draft.
        invalid = conn.execute("""SELECT 1 FROM platform_recipients r WHERE assignment_id=%s AND NOT EXISTS
            (SELECT 1 FROM course_memberships m WHERE m.course_id=%s AND m.user_id=r.student_id AND m.status='approved' AND m.course_role='student')""",
            (assignment_id, item["course_id"])).fetchone()
        if invalid:
            raise HTTPException(422, "A selected student is no longer enrolled. Update the draft's recipients.")
        try:
            snapshot = engines.publish_snapshot(item)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = conn.execute("UPDATE platform_assignments SET status='published', snapshot=%s, published_at=now(),updated_at=now() WHERE id=%s RETURNING *",
                           (Jsonb(snapshot), assignment_id)).fetchone()
        return public_assignment(row, True)


@router.post("/assignments/{assignment_id}/archive")
def archive(assignment_id: UUID, account=Depends(professor)):
    with store.connection() as conn:
        get_assignment(conn, assignment_id, account, manage=True, lock=True)
        conn.execute("UPDATE platform_assignments SET status='archived', updated_at=now() WHERE id=%s", (assignment_id,))
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
        return public_attempt(conn.execute("SELECT * FROM platform_attempts WHERE assignment_id=%s AND student_id=%s", (assignment_id, account["user_id"])).fetchone())


@router.post("/assignments/{assignment_id}/start")
def start(assignment_id: UUID, account=Depends(user)):
    with store.locked_attempt(assignment_id, account["user_id"]) as (conn, attempt):
        assignment = get_assignment(conn, assignment_id, account)
        if attempt:
            return public_attempt(attempt)
        # Deterministic identity lets engine starts recover from a lost gateway response.
        aid = uuid5(NAMESPACE_URL, f"cluball:{assignment_id}:{account['user_id']}")
        attempt = conn.execute("INSERT INTO platform_attempts(id,assignment_id,student_id) VALUES (%s,%s,%s) RETURNING *", (aid, assignment_id, account["user_id"])).fetchone()
        state = (adaptive_runtime.start(conn, assignment, attempt)
                 if adaptive_runtime.is_adaptive_assignment(assignment)
                 else engines.start(assignment, attempt))
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
        state = (adaptive_runtime.process_message(conn, assignment, attempt, body.message, rid)
                 if adaptive_runtime.is_adaptive_assignment(assignment)
                 else engines.message(assignment, attempt, body.message, rid))
        apply_state(attempt, state, body.message)
        attempt["processed_requests"].append(rid)
        store.save_attempt(conn, attempt)
        return public_attempt(attempt)


@router.get("/assignments/{assignment_id}/learning-analytics")
def learning_analytics(assignment_id: UUID, account=Depends(professor)):
    with store.connection() as conn:
        get_assignment(conn, assignment_id, account, manage=True)
        objectives = conn.execute(
            """SELECT objective_id,concept_id,status,count(*)::int AS students
               FROM platform_objective_progress WHERE assignment_id=%s
               GROUP BY objective_id,concept_id,status ORDER BY objective_id,status""",
            (assignment_id,),
        ).fetchall()
        misconceptions = conn.execute(
            """SELECT objective_id,misconception_code,count(*)::int AS occurrences
               FROM platform_learning_evidence
               WHERE assignment_id=%s AND misconception_code IS NOT NULL
               GROUP BY objective_id,misconception_code
               ORDER BY occurrences DESC,objective_id""",
            (assignment_id,),
        ).fetchall()
        remediation = conn.execute(
            """SELECT d.objective_id,count(*)::int AS decisions
               FROM platform_adaptive_decisions d
               JOIN platform_attempts a ON a.id=d.attempt_id
               WHERE a.assignment_id=%s AND d.action='REMEDIATE'
               GROUP BY d.objective_id""",
            (assignment_id,),
        ).fetchall()
    return {"objectives": objectives, "misconceptions": misconceptions, "remediation": remediation}


@router.post("/assignments/{assignment_id}/actions")
def action(assignment_id: UUID, body: ActionInput, account=Depends(user)):
    with store.locked_attempt(assignment_id, account["user_id"]) as (conn, attempt):
        assignment = get_assignment(conn, assignment_id, account)
        if not attempt or assignment["tool"] != "student-agent":
            raise HTTPException(409, "Start a tutor assignment first.")
        rid = str(body.request_id)
        if rid in attempt["processed_requests"]:
            return public_attempt(attempt)
        if attempt["status"] == "completed":
            raise HTTPException(409, "This assignment is already completed.")
        if body.action == "scenario" and attempt["engine_state"].get("phase") != "practice":
            raise HTTPException(422, "Reach the practice phase before choosing a scenario.")
        state = engines.call("student-agent", "POST", "/internal/platform/action", json={
            "session_id": str(attempt["id"]), "action": body.action, "value": body.value, "request_id": rid})
        apply_state(attempt, state)
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
        if assignment["tool"] == "student-agent":
            if adaptive_runtime.is_adaptive_assignment(assignment):
                attempt["engine_state"]["assignment_completed"] = True
            else:
                apply_state(attempt, result.copy())
                result = {"phase": result.get("phase"), "ended": True}
        attempt["result"] = result
        attempt["status"] = "completed"
        store.save_attempt(conn, attempt)
        return public_attempt(attempt)
