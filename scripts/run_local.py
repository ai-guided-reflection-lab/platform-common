"""Run all three APIs using each project's own environment, one public entry point."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


def main():
    for key in ('DATABASE_URL', 'REFLECTIONS_DATABASE_URL', 'AUTH_SESSION_SECRET', 'PLATFORM_SERVICE_TOKEN'):
        if not os.getenv(key):
            raise SystemExit(f'Set {key} in .env first.')
    if not (ROOT / 'platform_frontend/dist/index.html').exists():
        raise SystemExit('Build the UI first: cd platform_frontend && npm ci && npm run build')
    # Separate processes avoid the two projects' conflicting `app` package names.
    configs = [
        (ROOT, sys.executable, 'platform_app.main:app', '8000', os.environ.copy()),
        (ROOT / 'reflections-app/backend', os.getenv('REFLECTIONS_PYTHON', sys.executable), 'app.main:app', '8002', {**os.environ, 'DATABASE_URL': os.environ['REFLECTIONS_DATABASE_URL']}),
        (ROOT / 'student-agent-bot', os.getenv('TUTOR_PYTHON', sys.executable), 'app:app', '8003', os.environ.copy()),
    ]
    processes = []
    def stop(*_):
        for p in processes:
            if p.poll() is None: p.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for cwd, python, target, port, env in configs:
            processes.append(subprocess.Popen([python, '-m', 'uvicorn', target, '--host', '127.0.0.1', '--port', port], cwd=cwd, env=env))
        print('ClubALL is opening at http://127.0.0.1:8000', flush=True)
        while all(p.poll() is None for p in processes): time.sleep(.5)
    finally:
        stop()
        for p in processes:
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: p.kill()


if __name__ == '__main__': main()
