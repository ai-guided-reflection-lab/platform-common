from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from starlette.requests import Request

from app import auth, db, main, settings
from app.main import _verify_google_credential


def _request_with_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode("ascii"))],
        }
    )


class SessionTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_secret = settings.AUTH_SESSION_SECRET
        self.original_minutes = settings.AUTH_SESSION_MINUTES
        settings.AUTH_SESSION_SECRET = "test-secret-that-is-not-used-outside-tests"
        settings.AUTH_SESSION_MINUTES = 60

    def tearDown(self) -> None:
        settings.AUTH_SESSION_SECRET = self.original_secret
        settings.AUTH_SESSION_MINUTES = self.original_minutes

    def test_issued_session_verifies_user(self) -> None:
        token, expires_in = auth.issue_session("user-123")
        self.assertEqual(auth.verify_session(token)["sub"], "user-123")
        self.assertEqual(expires_in, 3600)

    def test_modified_session_is_rejected(self) -> None:
        token, _ = auth.issue_session("user-123")
        payload, signature = token.split(".", 1)
        modified = f"{payload}x.{signature}"
        with self.assertRaises(HTTPException) as context:
            auth.verify_session(modified)
        self.assertEqual(context.exception.status_code, 401)


class UserProfileTests(unittest.TestCase):
    def test_profile_includes_display_name(self) -> None:
        profile = db._user_profile(("user-123", "student", "student@charlotte.edu", "Student Name", 42, "student-gh"))
        self.assertIsNotNone(profile)
        self.assertEqual(profile["display_name"], "Student Name")
        self.assertEqual(profile["github_username"], "student-gh")

    def test_profile_includes_authority_and_pending_role(self) -> None:
        profile = db._user_profile(
            ("user-123", "student", "student@charlotte.edu", "Student Name", None, None, 2, 1, object())
        )
        self.assertEqual(profile["authority_level"], 2)
        self.assertEqual(profile["role"], "student")
        self.assertEqual(profile["requested_role"], "instructor")
        self.assertEqual(profile["role_status"], "pending")
        self.assertTrue(profile["onboarding_complete"])


class SchoolGoogleAccountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_client_id = settings.GOOGLE_CLIENT_ID
        self.original_enabled = settings.SCHOOL_GOOGLE_AUTH_ENABLED
        self.original_domains = settings.ALLOWED_GOOGLE_DOMAINS
        settings.GOOGLE_CLIENT_ID = "client.apps.googleusercontent.com"
        settings.SCHOOL_GOOGLE_AUTH_ENABLED = True
        settings.ALLOWED_GOOGLE_DOMAINS = {"charlotte.edu"}

    def tearDown(self) -> None:
        settings.GOOGLE_CLIENT_ID = self.original_client_id
        settings.SCHOOL_GOOGLE_AUTH_ENABLED = self.original_enabled
        settings.ALLOWED_GOOGLE_DOMAINS = self.original_domains

    @patch("app.main.google_id_token.verify_oauth2_token")
    def test_charlotte_workspace_account_is_allowed(self, verify_token) -> None:
        verify_token.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-1",
            "email": "student@charlotte.edu",
            "email_verified": True,
            "hd": "charlotte.edu",
        }
        profile = _verify_google_credential("credential")
        self.assertEqual(profile["email"], "student@charlotte.edu")

    @patch("app.main.google_id_token.verify_oauth2_token")
    def test_personal_google_account_is_rejected(self, verify_token) -> None:
        verify_token.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-2",
            "email": "student@gmail.com",
            "email_verified": True,
        }
        with self.assertRaises(HTTPException) as context:
            _verify_google_credential("credential")
        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("UNC Charlotte Google account", context.exception.detail)
        self.assertIn("@charlotte.edu", context.exception.detail)


class PasswordLoginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_secret = settings.AUTH_SESSION_SECRET
        self.original_enabled = settings.ALLOW_PASSWORD_LOGIN
        self.original_school_auth = settings.SCHOOL_GOOGLE_AUTH_ENABLED
        settings.AUTH_SESSION_SECRET = "test-secret-that-is-not-used-outside-tests"
        settings.ALLOW_PASSWORD_LOGIN = True
        settings.SCHOOL_GOOGLE_AUTH_ENABLED = True

    def tearDown(self) -> None:
        settings.AUTH_SESSION_SECRET = self.original_secret
        settings.ALLOW_PASSWORD_LOGIN = self.original_enabled
        settings.SCHOOL_GOOGLE_AUTH_ENABLED = self.original_school_auth

    @patch("app.main.db.is_enabled", return_value=True)
    @patch("app.main.db.authenticate_user")
    def test_verified_school_user_can_login_with_id_and_password(self, authenticate_user, _is_enabled) -> None:
        authenticate_user.return_value = {
            "user_id": "school-user-1",
            "username": "student1",
            "display_name": "Student One",
            "email": "student@charlotte.edu",
            "authority_level": 2,
            "role": "student",
            "role_status": "active",
            "onboarding_complete": True,
        }
        response = asyncio.run(main.login(main.LoginRequest(identifier="student1", password="password123")))
        self.assertEqual(response.user.username, "student1")
        authenticate_user.assert_called_once_with("student1", "password123", require_google=True)


class OnboardingTests(unittest.TestCase):
    @patch("app.db.get_user_by_id")
    @patch("app.db.get_connection")
    @patch("app.db._hash_password", return_value=("salt", "hash"))
    @patch("app.db.init_db")
    def test_student_onboarding_casts_null_authority_as_smallint(
        self,
        _init_db,
        _hash_password,
        get_connection,
        get_user_by_id,
    ) -> None:
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(None, 2), None]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value.__enter__.return_value = connection
        get_user_by_id.return_value = {
            "user_id": "student-user-1",
            "username": "student1",
            "display_name": "Student One",
            "email": "student@charlotte.edu",
            "authority_level": 2,
            "role": "student",
            "role_status": "active",
            "onboarding_complete": True,
        }

        user = db.complete_onboarding("student-user-1", "student1", "password123", "student")

        update_sql, update_params = cursor.execute.call_args_list[2].args
        self.assertIn("NULL::SMALLINT", update_sql)
        self.assertIn("%s::SMALLINT", update_sql)
        self.assertIsNone(update_params[4])
        self.assertEqual(user["role"], "student")


class GitHubAccountRequirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_secret = settings.AUTH_SESSION_SECRET
        self.original_required = settings.REQUIRE_GITHUB_ACCOUNT
        self.original_client_id = settings.GITHUB_CLIENT_ID
        self.original_client_secret = settings.GITHUB_CLIENT_SECRET
        self.original_callback_url = settings.GITHUB_CALLBACK_URL
        settings.AUTH_SESSION_SECRET = "test-secret-that-is-not-used-outside-tests"
        settings.REQUIRE_GITHUB_ACCOUNT = True
        settings.GITHUB_CLIENT_ID = "github-client-id"
        settings.GITHUB_CLIENT_SECRET = "github-client-secret"
        settings.GITHUB_CALLBACK_URL = "https://api.example.com/api/auth/github/callback"

    def tearDown(self) -> None:
        settings.AUTH_SESSION_SECRET = self.original_secret
        settings.REQUIRE_GITHUB_ACCOUNT = self.original_required
        settings.GITHUB_CLIENT_ID = self.original_client_id
        settings.GITHUB_CLIENT_SECRET = self.original_client_secret
        settings.GITHUB_CALLBACK_URL = self.original_callback_url

    @patch("app.main.db.get_user_by_id", return_value={"onboarding_complete": True})
    @patch("app.main.db.user_has_github", return_value=False)
    def test_unlinked_github_account_cannot_use_protected_routes(self, _has_github, _get_user) -> None:
        token, _ = auth.issue_session("school-user-1")
        with self.assertRaises(HTTPException) as context:
            main._current_user_id(_request_with_token(token))
        self.assertEqual(context.exception.status_code, 403)

    @patch("app.main.db.get_user_by_id", return_value={"onboarding_complete": True})
    @patch("app.main.db.user_has_github", return_value=True)
    def test_linked_github_account_can_use_protected_routes(self, _has_github, _get_user) -> None:
        token, _ = auth.issue_session("school-user-1")
        user_id = main._current_user_id(_request_with_token(token))
        self.assertEqual(user_id, "school-user-1")

    @patch("app.main.db.create_github_oauth_state", return_value="one-time-state")
    def test_github_start_uses_callback_and_state(self, create_state) -> None:
        token, _ = auth.issue_session("school-user-1")
        response = asyncio.run(main.github_start(_request_with_token(token)))
        parsed = urlparse(response.authorize_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "github.com")
        self.assertEqual(query["client_id"], ["github-client-id"])
        self.assertEqual(query["redirect_uri"], [settings.GITHUB_CALLBACK_URL])
        self.assertEqual(query["state"], ["one-time-state"])
        self.assertNotIn("scope", query)
        create_state.assert_called_once_with("school-user-1")

    @patch("app.main.requests.post")
    @patch("app.main.db.consume_github_oauth_state", return_value=None)
    def test_invalid_github_state_is_rejected_before_token_exchange(self, _consume_state, post) -> None:
        response = asyncio.run(main.github_callback(code="code", state="invalid-state"))
        self.assertIn("github=invalid_state", response.headers["location"])
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
