import importlib
import os

import httpx
from fastapi.testclient import TestClient


def headers(user):
    return {"X-Demo-User": user}


def test_complete_standalone_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ADAPTIVE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ADAPTIVE_AI_MODE", "demo")

    from app import config, db, main, openai_client, rag

    importlib.reload(config)
    importlib.reload(openai_client)
    importlib.reload(db)
    importlib.reload(rag)
    importlib.reload(main)

    with TestClient(main.app) as client:
        users = client.get("/api/demo/users").json()
        assert {user["role"] for user in users} == {"instructor", "student"}

        generated = client.post(
            "/api/instructor/generate-plan",
            headers=headers("instructor-demo"),
            json={"topic": "Large Language Models", "course_level": "Undergraduate"},
        )
        assert generated.status_code == 200
        assert len(generated.json()["objectives"]) >= 2
        assert "Large Language Models" in generated.json()["title"]

        assignments = client.get("/api/instructor/assignments", headers=headers("instructor-demo")).json()
        assignment_id = assignments[0]["id"]
        progress = client.get(
            f"/api/instructor/assignments/{assignment_id}/progress",
            headers=headers("instructor-demo"),
        )
        assert progress.status_code == 200
        assert len(progress.json()) == 2

        student_list = client.get("/api/student/assignments", headers=headers("student-alex")).json()
        assert student_list[0]["id"] == assignment_id
        attempt = client.post(
            f"/api/student/assignments/{assignment_id}/start",
            headers=headers("student-alex"),
        ).json()
        assert attempt["messages"][0]["role"] == "assistant"

        first = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-alex"),
            json={"content": "The first is functional because it describes system behavior, whereas the two-second limit is a measurable non-functional quality constraint."},
        )
        assert first.status_code == 200
        assert first.json()["current_objective"] == 1

        second = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-alex"),
            json={"content": "Quickly is ambiguous because it is not measurable. The search page shall show results within two seconds for 95 percent of requests."},
        )
        assert second.status_code == 200
        assert second.json()["required_task_status"] == "ready"

        completed = client.post(
            f"/api/student/assignments/{assignment_id}/submit-task",
            headers=headers("student-alex"),
            json={"content": "My completed requirements review includes classifications, findings, and measurable revisions."},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        detail = client.get(
            f"/api/instructor/assignments/{assignment_id}/students/student-alex",
            headers=headers("instructor-demo"),
        )
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["student"]["display_name"] == "Alex Morgan"
        assert detail_body["attempt"]["required_task_submission"].startswith("My completed")
        assert len(detail_body["attempt"]["messages"]) >= 5
        assert len(detail_body["evidence"]) == 2
        assert all(item["demonstrated"] for item in detail_body["evidence"])
        assert "Alex Morgan" in detail_body["summary"]["overview"]
        assert detail_body["summary"]["strengths"]
        assert detail_body["summary"]["weaknesses"]
        assert detail_body["summary"]["improvements"]


def test_uploaded_course_document_is_retrieved(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", str(tmp_path / "rag.sqlite3"))
    monkeypatch.setenv("ADAPTIVE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ADAPTIVE_AI_MODE", "demo")

    from app import config, db, main, openai_client, rag

    importlib.reload(config)
    importlib.reload(openai_client)
    importlib.reload(db)
    importlib.reload(rag)
    importlib.reload(main)

    with TestClient(main.app) as client:
        seeded = client.get(
            "/api/instructor/assignments", headers=headers("instructor-demo")
        ).json()[0]
        created = client.post(
            "/api/instructor/assignments",
            headers=headers("instructor-demo"),
            json={
                "title": "RAG assignment",
                "instructions": "Use the uploaded course material.",
                "student_ids": ["student-jordan"],
                "learning_plan": seeded["learning_plan"],
            },
        )
        assert created.status_code == 201
        assignment_id = created.json()["id"]

        upload = client.post(
            f"/api/instructor/assignments/{assignment_id}/documents",
            headers=headers("instructor-demo"),
            files={
                "file": (
                    "requirements-notes.txt",
                    b"A functional requirement describes system behavior. A non-functional requirement describes a quality attribute or constraint.",
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 201
        assert upload.json()["chunk_count"] == 1
        assert client.post(
            f"/api/instructor/assignments/{assignment_id}/publish",
            headers=headers("instructor-demo"),
        ).status_code == 200
        assert client.post(
            f"/api/student/assignments/{assignment_id}/start",
            headers=headers("student-jordan"),
        ).status_code == 200
        reply = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={
                "content": "The email receipt is functional because it is behavior, while the response time is a measurable quality constraint.",
            },
        )
        assert reply.status_code == 200
        assistant_message = reply.json()["messages"][-1]
        assert assistant_message["sources"][0]["filename"] == "requirements-notes.txt"


def test_openai_auth_failure_activates_demo_fallback(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_AI_MODE", "openai")
    monkeypatch.setenv("ADAPTIVE_ALLOW_DEMO_FALLBACK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-invalid")

    from app import config, openai_client

    importlib.reload(config)
    importlib.reload(openai_client)

    def unauthorized(*args, **kwargs):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(401, request=request, json={"error": {"message": "invalid key"}})

    monkeypatch.setattr(httpx.Client, "post", unauthorized)
    plan = openai_client.generate_learning_plan("Large Language Models", "Undergraduate")

    assert "Large Language Models" in plan["title"]
    assert openai_client.runtime_ai_mode() == "demo-fallback"


def test_demo_tutor_corrects_database_misconception_and_deduplicates_sources():
    from app.openai_client import _demo_assessment, _demo_tutor_reply
    from app.main import _source_metadata

    objective = {
        "title": "Explain Large Language Model fundamentals",
        "description": "Explain how an LLM generates text.",
        "success_criteria": ["Explains next-token prediction"],
    }
    response = "It queries a database and gives the answer."
    assessment = _demo_assessment(response, objective["success_criteria"], objective)
    sources = [
        {"document_id": "doc-1", "filename": "course.txt", "content": "First chunk", "score": 0.9},
        {"document_id": "doc-1", "filename": "course.txt", "content": "Second chunk", "score": 0.8},
    ]

    reply = _demo_tutor_reply(objective, response, assessment, sources, None)

    assert not assessment["demonstrated"]
    assert "next-token prediction" in reply
    assert len(_source_metadata(sources)) == 1


def test_resource_discovery_corrects_topic_typo_and_uses_direct_sources():
    from app.resource_discovery import discover_resources

    resources = discover_resources("System arhcitecture")

    assert [item["provider"] for item in resources] == [
        "OpenStax", "Open University", "Microsoft Learn"
    ]
    assert all("search" not in item["url"].lower() for item in resources)


def test_generated_assignment_study_quiz_and_adaptive_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", str(tmp_path / "placement.sqlite3"))
    monkeypatch.setenv("ADAPTIVE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ADAPTIVE_AI_MODE", "demo")

    from app import config, db, main, openai_client, rag

    importlib.reload(config)
    importlib.reload(openai_client)
    importlib.reload(db)
    importlib.reload(rag)
    importlib.reload(main)

    with TestClient(main.app) as client:
        plan = client.post(
            "/api/instructor/generate-plan",
            headers=headers("instructor-demo"),
            json={"topic": "Large Language Models", "course_level": "Undergraduate"},
        ).json()
        assert len(plan["study_resources"]) == 3
        assert {item["provider"] for item in plan["study_resources"]} == {
            "Google for Developers", "IBM", "AWS"
        }
        assert len(plan["diagnostic_quiz"]) == 5
        assert len(plan["learning_assets"]) == len(plan["objectives"])

        created = client.post(
            "/api/instructor/assignments",
            headers=headers("instructor-demo"),
            json={
                "title": "LLM learning path",
                "instructions": "Study, take the diagnostic, and demonstrate each objective.",
                "student_ids": ["student-jordan"],
                "learning_plan": plan,
            },
        )
        assignment_id = created.json()["id"]
        client.post(
            f"/api/instructor/assignments/{assignment_id}/publish",
            headers=headers("instructor-demo"),
        )
        refreshed = client.post(
            f"/api/instructor/assignments/{assignment_id}/refresh-resources",
            headers=headers("instructor-demo"),
        ).json()
        assert len(refreshed["learning_plan"]["study_resources"]) == 3

        started = client.post(
            f"/api/student/assignments/{assignment_id}/start",
            headers=headers("student-jordan"),
        ).json()
        assert started["phase"] == "study_resources"
        assert started["messages"] == []

        studied = client.post(
            f"/api/student/assignments/{assignment_id}/study-complete",
            headers=headers("student-jordan"),
            json={"message": "I'm back and I've studied it"},
        ).json()
        assert studied["phase"] == "diagnostic_quiz"

        quiz = client.post(
            f"/api/student/assignments/{assignment_id}/quiz",
            headers=headers("student-jordan"),
            json={"answers": [1, 1, 1, 1, 1]},
        ).json()
        assert quiz["quiz_score"] <= 2
        assert quiz["learning_path"] == "foundational"
        assert quiz["phase"] == "adaptive_learning"
        assert quiz["learning_state"]["mode"] == "practice"
        assert quiz["learning_state"]["practice_level"] == "foundational"
        assert set(quiz["learning_state"]["objective_paths"].values()) == {"foundational"}

        practice = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": "A token is a text unit, and the model predicts which token is likely next because it learned language patterns."},
        ).json()
        assert practice["current_objective"] == 0
        if practice["learning_state"]["mode"] == "practice":
            practice = client.post(
                f"/api/student/assignments/{assignment_id}/messages",
                headers=headers("student-jordan"),
                json={"content": "An LLM stores learned statistical patterns in parameters and generates an answer token by token instead of retrieving one complete database record."},
            ).json()
        assert practice["learning_state"]["mode"] == "demonstration"

        progress = client.get(
            f"/api/instructor/assignments/{assignment_id}/progress",
            headers=headers("instructor-demo"),
        ).json()[0]
        assert progress["study_completed_at"]
        assert progress["quiz_score"] == quiz["quiz_score"]
        assert progress["learning_path"] == "foundational"


def test_advanced_and_struggling_student_personas_follow_defined_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", str(tmp_path / "personas.sqlite3"))
    monkeypatch.setenv("ADAPTIVE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ADAPTIVE_AI_MODE", "demo")

    from app import config, db, main, openai_client, rag

    importlib.reload(config)
    importlib.reload(openai_client)
    importlib.reload(db)
    importlib.reload(rag)
    importlib.reload(main)

    with TestClient(main.app) as client:
        plan = client.post(
            "/api/instructor/generate-plan",
            headers=headers("instructor-demo"),
            json={"topic": "Large Language Models", "course_level": "Undergraduate"},
        ).json()
        created = client.post(
            "/api/instructor/assignments",
            headers=headers("instructor-demo"),
            json={
                "title": "Persona path test",
                "instructions": "Verify the adaptive path.",
                "student_ids": ["student-alex", "student-jordan"],
                "learning_plan": plan,
            },
        )
        assignment_id = created.json()["id"]
        assert client.post(
            f"/api/instructor/assignments/{assignment_id}/publish",
            headers=headers("instructor-demo"),
        ).status_code == 200

        correct_answers = [item["correct_index"] for item in plan["diagnostic_quiz"]]
        wrong_answers = [(answer + 1) % 4 for answer in correct_answers]

        def reach_quiz(student_id, answers):
            client.post(
                f"/api/student/assignments/{assignment_id}/start",
                headers=headers(student_id),
            )
            client.post(
                f"/api/student/assignments/{assignment_id}/study-complete",
                headers=headers(student_id),
                json={"message": "I have finished studying and I am ready"},
            )
            response = client.post(
                f"/api/student/assignments/{assignment_id}/quiz",
                headers=headers(student_id),
                json={"answers": answers},
            )
            assert response.status_code == 200, response.text
            return response.json()

        advanced = reach_quiz("student-alex", correct_answers)
        assert advanced["learning_path"] == "accelerated"
        assert advanced["learning_state"]["current_path"] == "accelerated"
        assert advanced["learning_state"]["mode"] == "demonstration"
        assert advanced["messages"][-1]["content"].startswith(
            "You scored 5 out of 5. Your starting path is accelerated.\n\nChallenge:"
        )

        strong_answer = (
            "A language model predicts the next token from context because its learned "
            "parameters represent statistical language patterns; therefore fluent output "
            "still needs factual verification with reliable evidence."
        )
        advanced_next = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-alex"),
            json={"content": strong_answer},
        ).json()
        assert advanced_next["current_objective"] == 1
        assert advanced_next["learning_state"]["current_path"] == "accelerated"

        struggling = reach_quiz("student-jordan", wrong_answers)
        assert struggling["learning_path"] == "foundational"
        assert struggling["learning_state"]["mode"] == "practice"
        assert struggling["learning_state"]["practice_level"] == "foundational"

        misconception = "It queries a database and gives the stored answer."
        first_practice = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": misconception},
        ).json()
        assert first_practice["learning_state"]["mode"] == "practice"
        assert first_practice["learning_state"]["practice_index"] == 1

        demonstration = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": "I do not know."},
        ).json()
        assert demonstration["learning_state"]["mode"] == "demonstration"

        first_failure = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": misconception},
        ).json()
        assert first_failure["learning_state"]["failures"] == 1

        resumed = client.get(
            f"/api/student/assignments/{assignment_id}/attempt",
            headers=headers("student-jordan"),
        ).json()
        assert resumed["learning_state"] == first_failure["learning_state"]

        remediated = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": misconception},
        ).json()
        assert remediated["learning_state"]["mode"] == "practice"
        assert remediated["learning_state"]["practice_level"] == "foundational"
        assert "strengthen the foundation" in remediated["messages"][-1]["content"]

        recovered_practice = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": strong_answer},
        ).json()
        assert recovered_practice["learning_state"]["mode"] == "demonstration"
        assert recovered_practice["current_objective"] == 0

        recovered = client.post(
            f"/api/student/assignments/{assignment_id}/messages",
            headers=headers("student-jordan"),
            json={"content": strong_answer},
        ).json()
        assert recovered["current_objective"] == 1
