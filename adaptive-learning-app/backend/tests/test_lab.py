import hashlib
import pytest
from fastapi.testclient import TestClient
from test_api import client, create, lesson, headers


@pytest.fixture
def lab_client(client, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_LAB_MODE", "true")
    monkeypatch.setenv("ADAPTIVE_LAB_INSTRUCTOR_ID", "instructor-demo")
    return client


def join(client, name="Taylor"):
    response = client.post("/api/lab/sessions", json={"name": name})
    assert response.status_code == 201, response.text
    result = response.json()
    return result, {"Authorization": "Bearer " + result["token"]}


def test_lab_is_disabled_by_default(client, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_LAB_MODE", "false")
    assert client.post("/api/lab/sessions", json={"name": "Taylor"}).status_code == 404


def test_normal_instructor_publishes_stable_unique_codes(client, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_LAB_MODE", "false")
    first = create(client)
    second = create(client)
    draft = create(client, publish=False)
    def detail(aid):
        return client.get(f"/api/instructor/assignments/{aid}", headers=headers("instructor-demo")).json()
    code = detail(first)["access_code"]
    assert code and code != detail(second)["access_code"]
    assert detail(first)["access_code"] == code
    assert "access_code" not in detail(draft)
    monkeypatch.setenv("ADAPTIVE_LAB_MODE", "true")
    _, participant = join(client)
    result = client.post("/api/lab/redeem", headers=participant, json={"code": code})
    assert result.status_code == 200
    assert result.json()["assignment_id"] == first


def test_code_collision_retries_without_replacing_existing_code(client, monkeypatch):
    from app import lab
    monkeypatch.setenv("ADAPTIVE_LAB_MODE", "false")
    first = create(client)
    existing = client.get(f"/api/instructor/assignments/{first}", headers=headers("instructor-demo")).json()["access_code"]
    candidates = iter([existing, "1234567890", "1234567890"])
    monkeypatch.setattr(lab.secrets, "token_hex", lambda size: next(candidates))
    second = create(client)
    assert lab.assignment_code(second) == "1234567890"


def test_sessions_are_private_and_names_do_not_merge(lab_client):
    first, h1 = join(lab_client)
    second, h2 = join(lab_client)
    assert first["user"]["id"] != second["user"]["id"]
    assert first["token"] != second["token"]
    from app.db import connection
    with connection() as conn:
        saved = conn.execute("SELECT token_hash FROM lab_sessions WHERE student_id=?", (first["user"]["id"],)).fetchone()
        assert saved["token_hash"] == hashlib.sha256(first["token"].encode()).hexdigest()
    assert lab_client.get("/api/lab/session", headers=h1).json()["id"] == first["user"]["id"]
    assert lab_client.get("/api/lab/session", headers={"Authorization": "Bearer invalid", **headers("instructor-demo")}).status_code == 401
    assert lab_client.post("/api/lab/sessions", json={"name": " "}).status_code == 422


def test_publication_enrollment_progress_and_archive(lab_client):
    published = create(lab_client)
    draft = create(lab_client, publish=False)
    first, h1 = join(lab_client)
    second, h2 = join(lab_client)
    assert lab_client.get("/api/student/assignments", headers=h1).json() == []
    assert lab_client.get(f"/api/student/assignments/{published}", headers=h1).status_code == 404
    code = lab_client.get(f"/api/instructor/assignments/{published}", headers=headers("instructor-demo")).json()["access_code"]
    assert lab_client.post("/api/lab/redeem", headers=h1, json={"code":"wrong"}).status_code == 404
    for h in (h1,h2):
        assert lab_client.post("/api/lab/redeem", headers=h, json={"code":code.lower()}).status_code == 200
    assert lab_client.post("/api/lab/redeem", headers=h1, json={"code":" " + code + " "}).status_code == 200
    assert lab_client.get(f"/api/instructor/assignments/{published}", headers=headers("instructor-demo")).json()["access_code"] == code
    items = lab_client.get("/api/student/assignments", headers=h1).json()
    assert published in {item["id"] for item in items}
    assert draft not in {item["id"] for item in items}
    assert lab_client.get(f"/api/student/assignments/{draft}", headers=h1).status_code == 404
    a = lab_client.post(f"/api/student/assignments/{published}/start", headers=h1)
    b = lab_client.post(f"/api/student/assignments/{published}/start", headers=h2)
    assert a.status_code == b.status_code == 200
    assert a.json()["id"] != b.json()["id"]
    assert lab_client.post(f"/api/student/assignments/{published}/start", headers=h1).json()["id"] == a.json()["id"]
    assert lab_client.post(f"/api/student/assignments/{published}/learning-turn", headers=h1,
                           json={"action": "continue", "turn_id": "lab-test-turn"}).status_code == 200
    students = lab_client.get(f"/api/instructor/assignments/{published}", headers=headers("instructor-demo")).json()["students"]
    assert first["user"]["id"] in {student["id"] for student in students}
    assert lab_client.get("/api/instructor/assignments", headers=h1).status_code == 403
    newly_published = create(lab_client)
    assert newly_published not in {item["id"] for item in lab_client.get("/api/student/assignments", headers=h1).json()}
    from app.db import connection
    with connection() as conn:
        conn.execute("UPDATE assignments SET status='archived' WHERE id=?", (published,))
    assert lab_client.get(f"/api/student/assignments/{published}", headers=h1).status_code == 404
    assert lab_client.post("/api/lab/redeem", headers=h1, json={"code":code}).status_code == 404


def test_gateway_blocks_private_routes_and_demo_identity():
    import lab_gateway
    with TestClient(lab_gateway.app) as gateway:
        for route in ("/api/instructor/assignments", "/api/demo/users", "/internal/platform/students/resolve", "/docs", "/openapi.json"):
            assert gateway.get(route).status_code == 404
        assert gateway.get("/api/student/assignments", headers=headers("instructor-demo")).status_code == 401
        assert gateway.post("/api/student/assignments/a/not-a-student-action").status_code == 404
