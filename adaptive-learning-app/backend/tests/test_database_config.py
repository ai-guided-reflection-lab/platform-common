"""Check database selection without connecting to or changing shared data."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def load_config(tmp_path, monkeypatch):
    for key in ("DATABASE_URL", "DATABASE_SCHEMA", "SELF_DIRECTED_LEARNING_DB_SCHEMA",
                "ADAPTIVE_DATABASE_PATH", "PLATFORM_SERVICE_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "adaptive-learning-app/backend/app/config.py"
    target.parent.mkdir(parents=True)
    target.write_text((Path(__file__).parents[1] / "app/config.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://shared.invalid/main\n"
        "SELF_DIRECTED_LEARNING_DB_SCHEMA=self_directed_learning\n"
        "PLATFORM_SERVICE_TOKEN=shared-test-token\n", encoding="utf-8")
    (tmp_path / "adaptive-learning-app/.env").write_text(
        "DATABASE_URL=postgresql://other.invalid/old\n"
        "DATABASE_SCHEMA=legacy_sdl\nPLATFORM_SERVICE_TOKEN=old-test-token\n", encoding="utf-8")

    def load():
        spec = importlib.util.spec_from_file_location("isolated_sdl_config", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # dotenv adds keys directly to os.environ; register their restoration first.
    for key in ("DATABASE_URL", "DATABASE_SCHEMA", "SELF_DIRECTED_LEARNING_DB_SCHEMA", "PLATFORM_SERVICE_TOKEN"):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    return load


def test_root_database_and_schema_override_stale_app_settings(load_config):
    config = load_config()
    assert config.DATABASE_URL == "postgresql://shared.invalid/main"
    assert config.DATABASE_SCHEMA == "self_directed_learning"


def test_process_database_takes_precedence(load_config, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://deployment.invalid/main")
    assert load_config().DATABASE_URL == "postgresql://deployment.invalid/main"


def test_explicit_sqlite_remains_available_for_offline_tests(load_config, monkeypatch, tmp_path):
    path = tmp_path / "offline.sqlite3"
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", str(path))
    config = load_config()
    assert config.DATABASE_URL == ""
    assert config.DATABASE_PATH == path


def test_empty_sqlite_override_uses_shared_postgres(load_config, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_DATABASE_PATH", "")
    assert load_config().DATABASE_URL == "postgresql://shared.invalid/main"


def test_sdl_provider_override_is_independent_of_platform_and_other_engines(load_config, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("ADAPTIVE_AI_MODE", "openai")
    monkeypatch.setenv("SDL_LLM_PROVIDER", "groq")
    monkeypatch.setenv("PLATFORM_AGENT_PROVIDER", "ollama")
    config = load_config()
    assert config.LLM_PROVIDER == "groq"
    assert config.AI_MODE == "groq"
