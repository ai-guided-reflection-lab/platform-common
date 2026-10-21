"""Initialize shared tables before starting a fresh Reflections deployment."""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    # Use a separate interpreter: the two backends both name their package app.
    subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'Socratic-Chat/backend'); "
         "from app import db; db.init_db(); "
         "from platform_app import store; store.migrate()"],
        cwd=ROOT, check=True,
    )
    os.chdir(ROOT / "reflections-app/backend")
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app",
                            "--host", "0.0.0.0", "--port", os.getenv("PORT", "10000")])
