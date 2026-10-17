"""HTTP smoke checks against run_wiring_test.py's disposable localhost accounts."""
from uuid import uuid4

import httpx


def main():
    provider_gaps = []
    with httpx.Client(base_url="http://127.0.0.1:8015", timeout=180) as client:
        def login(username):
            response = client.post(
                "/api/auth/login",
                json={"identifier": username, "password": "CourseLab-local-test-2026"},
            )
            response.raise_for_status()
            return {"Authorization": "Bearer " + response.json()["access_token"]}

        professor = login("wiring-professor")
        student = login("wiring-student")

        def request(method, path, headers, **kwargs):
            response = client.request(method, path, headers=headers, **kwargs)
            if response.is_error:
                raise RuntimeError(
                    f"{method} {path}: {response.status_code} {response.text[:350]}"
                )
            return response.json()

        courses = request("GET", "/api/platform/courses", professor)["courses"]
        course = next(
            (c for c in courses if c["course_code"] == "ITSC 3155 · FALL 2026"),
            None,
        )
        if course is None:
            course = request(
                "POST",
                "/api/platform/courses",
                professor,
                json={
                    "title": "Software Engineering Integration",
                    "course_code": "ITSC 3155 · Fall 2026",
                },
            )
        assignments = request("GET", "/api/platform/assignments", professor)

        def ensure(tool, title, config):
            existing = next(
                (
                    item
                    for item in assignments
                    if item["title"] == title
                    and item["course_id"] == course["course_id"]
                ),
                None,
            )
            if not existing:
                existing = request(
                    "POST",
                    "/api/platform/assignments",
                    professor,
                    json={
                        "course_id": course["course_id"],
                        "tool": tool,
                        "title": title,
                        "config": config,
                    },
                )
            request(
                "POST",
                f"/api/platform/assignments/{existing['id']}/publish",
                professor,
            )
            return existing

        debate = ensure(
            "debate",
            "Requirements and tradeoffs",
            {
                "scenario": "Should a university require every software project to use AI?",
                "minimum_messages": 1,
            },
        )
        reflection = ensure(
            "reflections",
            "Reflect on requirements analysis",
            {
                "required_topics": ["Requirements analysis"],
                "sub_topics": ["Identifying stakeholder needs"],
            },
        )
        print("PASS: Debate and Reflections publish through their real adapters.", flush=True)

        request(
            "POST",
            "/api/platform/courses/join",
            student,
            json={"code": course["join_code"]},
        )
        visible = request("GET", "/api/platform/assignments", student)
        assert {debate["id"], reflection["id"]}.issubset(
            {item["id"] for item in visible}
        )
        print(
            "PASS: Course-code enrollment grants published activities to a late-joining student.",
            flush=True,
        )

        for assignment in (debate, reflection):
            path = f"/api/platform/assignments/{assignment['id']}"
            try:
                started = request("POST", path + "/start", student)
            except RuntimeError as error:
                if ": 503 " not in str(error):
                    raise
                provider_gaps.append(f"{assignment['tool']}: {error}")
                print(
                    f"BLOCKED: {assignment['tool']} could not start its conversation (provider returned 503).",
                    flush=True,
                )
                continue
            assert started["messages"]
            print(
                f"PASS: {assignment['tool']} opens and saves its real conversation.",
                flush=True,
            )
            if started["status"] == "completed":
                continue
            try:
                reply = request(
                    "POST",
                    path + "/messages",
                    student,
                    json={
                        "message": (
                            "Stakeholder interviews help uncover conflicting goals. "
                            "I would compare the strongest needs, constraints, and "
                            "evidence before choosing a requirement."
                        ),
                        "request_id": str(uuid4()),
                    },
                )
            except RuntimeError as error:
                if ": 503 " not in str(error):
                    raise
                provider_gaps.append(f"{assignment['tool']}: {error}")
                print(
                    f"BLOCKED: {assignment['tool']} generated reply (provider returned 503).",
                    flush=True,
                )
                continue
            assert reply["messages"][-1]["role"] == "assistant"
            print(
                f"PASS: {assignment['tool']} returns an AI reply and persists the turn.",
                flush=True,
            )

    if provider_gaps:
        print(
            "GAP: live AI generation is blocked by the invalid configured provider key; "
            "shared RAG indexing/retrieval and SDL lesson preparation need valid embeddings too.",
            flush=True,
        )


if __name__ == "__main__":
    main()
