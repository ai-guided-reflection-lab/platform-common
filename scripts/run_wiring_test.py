"""Run the integrated UI with disposable accounts against a localhost database only.

Start pgvector/pgvector:pg16 on localhost:55439 first. No organization database is used.
"""
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from uuid import NAMESPACE_URL, uuid5
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATABASE = os.getenv("WIRING_TEST_DATABASE_URL", "postgresql://postgres:courselab-local-test-only@127.0.0.1:55439/courselab_wiring")
if urlsplit(DATABASE).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("The wiring test launcher only accepts a local database.")
os.environ.update(DATABASE_URL=DATABASE, PLATFORM_DB_SCHEMA="wiring_test_platform", SOCRATIC_DB_SCHEMA="wiring_test_socratic", SHARED_RAG_DB_SCHEMA="wiring_test_shared_rag",
    SELF_DIRECTED_LEARNING_DB_SCHEMA="wiring_test_sdl", REFLECTIONS_DB_SCHEMA="wiring_test_reflections",
    AUTH_SESSION_SECRET="local-wiring-test-session-secret-not-for-production", PLATFORM_SERVICE_TOKEN=secrets.token_urlsafe(48),
    AUTH_MODE="open", REQUIRE_GITHUB_ACCOUNT="false", SCHOOL_GOOGLE_AUTH_ENABLED="false",
    SELF_DIRECTED_LEARNING_URL="http://127.0.0.1:8115", REFLECTIONS_URL="http://127.0.0.1:8017",
    ADAPTIVE_PLATFORM_ONLY="true", WIRING_TEST_MODE="true", WIRING_PUBLIC_DEMO=os.getenv("WIRING_PUBLIC_DEMO", "false"), ADAPTIVE_UPLOAD_DIR=str(ROOT / ".test-wiring-uploads"))
os.environ.pop("ADAPTIVE_DATABASE_PATH", None)
sys.path.insert(0, str(ROOT))


def main():
    from platform_app.main import app
    from app import db
    from platform_app import store
    db.init_db()
    store.migrate()
    password = "CourseLab-local-test-2026"
    salt, hashed = db._hash_password(password)
    with store.connection() as conn:
        for username, name, role in [("wiring-professor", "Taylor Instructor", 1), ("wiring-student", "Alex Student", 2)]:
            conn.execute("""INSERT INTO users_platform(id,username,email,display_name,password_salt,password_hash,authority_level,onboarding_completed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT(username) DO NOTHING""",
                (uuid5(NAMESPACE_URL, "courselab-test:" + username), username, username + "@example.test", name, salt, hashed, role))
    processes = []
    docker_reflections = os.getenv("WIRING_REFLECTIONS_DOCKER", "true").lower() == "true"
    reflection_container = "courselab-wiring-reflections"

    def stop(*_):
        for process in processes:
            if process.poll() is None:
                process.terminate()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        services = [(ROOT,"platform_app.main:app",8015), (ROOT / "adaptive-learning-app/backend","app.main:app",8115)]
        if not docker_reflections:
            services.append((ROOT / "reflections-app/backend","app.main:app",8017))
        else:
            parsed=urlsplit(DATABASE)
            docker_database=urlunsplit(parsed._replace(netloc=parsed.netloc.replace(parsed.hostname,"host.docker.internal")))
            command=["docker","run","--rm","--name",reflection_container,"--publish","127.0.0.1:8017:8000",
                "--env","DATABASE_URL="+docker_database,
                "--env","PLATFORM_DB_SCHEMA=wiring_test_platform","--env","REFLECTIONS_DB_SCHEMA=wiring_test_reflections",
                "--env","PLATFORM_SERVICE_TOKEN"]
            # Default to no provider credentials. Live testing is an explicit opt-in.
            if os.getenv("WIRING_ENABLE_LIVE_AI") == "true":
                provider = os.getenv("LLM_PROVIDER", "groq").lower()
                command.extend(["--env","LLM_PROVIDER="+provider])
                allowed = {"groq":("GROQ_API_KEY","GROQ_MODEL"),"openai":("OPENAI_API_KEY","OPENAI_MODEL"),"ollama":("OLLAMA_URL","OLLAMA_MODEL")}.get(provider,())
                for key in allowed:
                    if os.getenv(key):command.extend(["--env",key])
            else:
                command.extend(["--env","LLM_PROVIDER=groq","--env","GROQ_API_KEY=","--env","OPENAI_API_KEY="])
            command.extend(["--volume",str(ROOT / "reflections-app/backend")+":/app:ro","reflection-app-v1-reflections:latest"])
            processes.append(subprocess.Popen(command,env=os.environ.copy()))
        for cwd, target, port in services:
            processes.append(subprocess.Popen([sys.executable,"-m","uvicorn",target,"--host","127.0.0.1","--port",str(port)],cwd=cwd,env=os.environ.copy()))
        print("Local integration: http://127.0.0.1:8015/platform/", flush=True)
        print("Disposable logins: wiring-professor / wiring-student; password: " + password, flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(.5)
    finally:
        if docker_reflections:
            subprocess.run(["docker","stop",reflection_container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        stop()
        for process in processes:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill()


if __name__ == "__main__":
    main()
