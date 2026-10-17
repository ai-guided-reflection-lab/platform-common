"""The platform launcher must not split services across databases."""
import importlib.util
from pathlib import Path


def test_services_share_database_and_sdl_ignores_inherited_sqlite(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "scripts/run_local.py"
    spec = importlib.util.spec_from_file_location("shared_database_launcher", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setenv("DATABASE_URL", "postgresql://shared.invalid/main")
    monkeypatch.setenv("REFLECTIONS_DATABASE_URL", "postgresql://old.invalid/reflections")
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", "old-local.sqlite3")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-session")
    monkeypatch.setenv("PLATFORM_SERVICE_TOKEN", "test-service")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    frontend = tmp_path / "platform_frontend/dist/index.html"
    frontend.parent.mkdir(parents=True)
    frontend.touch()
    launched = []

    class FinishedProcess:
        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    def launch(command, **kwargs):
        launched.append(kwargs)
        return FinishedProcess()

    monkeypatch.setattr(runner.subprocess, "Popen", launch)
    monkeypatch.setattr(runner.signal, "signal", lambda *args: None)
    runner.main()
    assert len(launched) == 3
    for index in (0, 1, 2):
        assert launched[index]["env"]["DATABASE_URL"] == "postgresql://shared.invalid/main"
    assert "ADAPTIVE_DATABASE_PATH" not in launched[2]["env"]
