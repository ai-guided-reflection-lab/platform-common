"""Credential-safe setup checks; no package installation or network access."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("demo_mode", Path(__file__).resolve().parents[1] / "demo_mode.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class DemoSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / ".env.example").write_text(
            "AUTH_SESSION_SECRET=replace-session\nPLATFORM_SERVICE_TOKEN=replace-service\n"
            "DATABASE_URL=postgresql://example\nOPENAI_API_KEY=\nDEMO_LLM_PROVIDER=openai\n")

    def test_creates_independent_secrets_and_leaves_external_credentials_empty(self):
        path = setup.prepare_env(self.root)
        values = dict(line.split("=", 1) for line in path.read_text().splitlines())
        self.assertGreater(len(values["AUTH_SESSION_SECRET"]), 40)
        self.assertNotEqual(values["AUTH_SESSION_SECRET"], values["PLATFORM_SERVICE_TOKEN"])
        self.assertEqual(values["DATABASE_URL"], "")
        self.assertEqual(setup.missing_credentials(path), ["DATABASE_URL", "OPENAI_API_KEY"])

    def test_preserves_existing_env_byte_for_byte(self):
        path = self.root / ".env"
        original = b'# Existing private config\r\nOPENAI_API_KEY="private-test-value"\r\n'
        path.write_bytes(original)
        setup.prepare_env(self.root)
        self.assertEqual(path.read_bytes(), original)

    def test_rerunning_preserves_generated_secrets(self):
        path = setup.prepare_env(self.root)
        original = path.read_bytes()
        setup.prepare_env(self.root)
        self.assertEqual(path.read_bytes(), original)

    def test_env_only_prints_path_and_missing_names_without_secrets(self):
        path = setup.prepare_env(self.root)
        secret = path.read_text().splitlines()[0].split("=", 1)[1]
        output = StringIO()
        with patch.object(setup, "ROOT", self.root), patch("sys.argv", ["demo_mode.py", "--env-only"]), redirect_stdout(output):
            self.assertEqual(setup.main(), 0)
        self.assertIn(path.as_posix(), output.getvalue())
        self.assertIn("DATABASE_URL, OPENAI_API_KEY", output.getvalue())
        self.assertNotIn(secret, output.getvalue())

    def test_missing_start_credentials_do_not_launch(self):
        with patch.object(setup, "ROOT", self.root), patch("sys.argv", ["demo_mode.py", "--env-only", "--start"]), patch.object(setup.subprocess, "call") as call, redirect_stdout(StringIO()):
            self.assertEqual(setup.main(), 2)
            call.assert_not_called()

    def test_runtime_versions(self):
        for value in ("v20.19.0", "v22.12.0", "v24.11.1"):
            self.assertTrue(setup.node_supported(value))
        for value in ("v18.20.0", "v20.18.0", "v21.0.0", "v22.1.0", "unknown"):
            self.assertFalse(setup.node_supported(value))


if __name__ == "__main__":
    unittest.main()
