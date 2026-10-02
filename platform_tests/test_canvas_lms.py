import httpx
import pytest

from platform_app import canvas_lms


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lists_paginated_active_courses_without_leaking_token():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"id": 2, "name": "Second"}])
        return httpx.Response(
            200,
            json=[{"id": 1, "name": "First", "course_code": "ITSC 3155"}],
            headers={
                "Link": '<https://instructure.charlotte.edu/api/v1/courses?page=2>; rel="next"'
            },
        )

    with mock_client(handler) as client:
        result = canvas_lms.list_courses("student-token", client=client)

    assert [course["id"] for course in result] == ["1", "2"]
    assert requests[0].url.params["enrollment_state"] == "active"
    assert requests[0].headers["Authorization"] == "Bearer student-token"
    assert "student-token" not in str(requests[0].url)


def test_rejects_pagination_outside_unc_charlotte_canvas():
    def handler(request):
        return httpx.Response(
            200,
            json=[],
            headers={"Link": '<https://attacker.example/api/v1/courses?page=2>; rel="next"'},
        )

    with mock_client(handler) as client, pytest.raises(canvas_lms.CanvasAPIError) as caught:
        canvas_lms.list_courses("student-token", client=client)

    assert caught.value.status_code == 502
    assert "unsafe pagination" in caught.value.detail


def test_maps_canvas_authentication_failure_to_validation_error():
    with mock_client(lambda request: httpx.Response(401, json={"errors": []})) as client:
        with pytest.raises(canvas_lms.CanvasAPIError) as caught:
            canvas_lms.list_courses("expired-token", client=client)

    assert caught.value.status_code == 422
    assert "rejected the access token" in caught.value.detail


def test_assignment_description_is_plain_text_and_exact_endpoint_is_used():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": 42,
                "name": "Architecture reflection",
                "description": "<p>Explain <strong>one</strong> tradeoff.</p><script>secret()</script>",
                "due_at": "2026-10-01T16:00:00Z",
                "html_url": "https://instructure.charlotte.edu/courses/7/assignments/42",
            },
        )

    with mock_client(handler) as client:
        assignment = canvas_lms.get_assignment(7, 42, "student-token", client=client)

    assert requests[0].url.path == "/api/v1/courses/7/assignments/42"
    assert assignment["description"] == "Explain one tradeoff."
    assert assignment["due_at"] == "2026-10-01T16:00:00Z"
