"""Start the isolated, persistent demo workspace using the root .env database."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env", override=True)
    for key in ("DATABASE_URL", "AUTH_SESSION_SECRET", "PLATFORM_SERVICE_TOKEN"):
        if not os.getenv(key):
            raise SystemExit(f"Set {key} in the root .env first.")
    os.environ.update(
        PLATFORM_DEMO_MODE="true", PLATFORM_DB_SCHEMA="demo_platform",
        SOCRATIC_DB_SCHEMA="demo_socratic", SHARED_RAG_DB_SCHEMA="demo_shared_rag",
        SELF_DIRECTED_LEARNING_DB_SCHEMA="demo_sdl", REFLECTIONS_DB_SCHEMA="demo_reflections",
        SELF_DIRECTED_LEARNING_URL="http://127.0.0.1:8115",
        AUTH_MODE="open", REQUIRE_GITHUB_ACCOUNT="false", REQUIRE_EMAIL_VERIFICATION="false",
        ADAPTIVE_PLATFORM_ONLY="true", WIRING_TEST_MODE="false", WIRING_PUBLIC_DEMO="false",
        LLM_PROVIDER=os.getenv("DEMO_LLM_PROVIDER", "openai"),
    )
    os.environ.pop("ADAPTIVE_DATABASE_PATH", None)
    processes = []

    def stop(*_):
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        for cwd, app, port in ((ROOT, "platform_app.main:app", 8015),
                               (ROOT / "adaptive-learning-app/backend", "app.main:app", 8115)):
            processes.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", app, "--host", "127.0.0.1", "--port", str(port)],
                cwd=cwd, env=os.environ.copy()))
        print("Demo workspace: http://127.0.0.1:8015/platform/", flush=True)
        print("Profiles persist in demo_* schemas. Student/Professor switching is profile-scoped.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
