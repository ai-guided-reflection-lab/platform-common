"""Repeatable demo setup. Uses only the standard library before creating .venv."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
DEPENDENCIES = (
    "requirements.txt", "Socratic-Chat/backend/requirements.txt",
    "adaptive-learning-app/backend/requirements.txt",
    "platform_frontend/package.json", "platform_frontend/package-lock.json",
)


def prepare_env(root):
    destination = root / ".env"
    if destination.exists():
        return destination
    replacements = {
        "DATABASE_URL": "",
        "AUTH_SESSION_SECRET": secrets.token_urlsafe(48),
        "PLATFORM_SERVICE_TOKEN": secrets.token_urlsafe(48),
        "DEMO_LLM_PROVIDER": "openai",
    }
    lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    result = []
    for line in lines:
        name = line.partition("=")[0].strip()
        if name in replacements:
            line = name + "=" + replacements.pop(name)
        result.append(line)
    result.extend(name + "=" + value for name, value in replacements.items())
    # Exclusive creation also protects an .env created concurrently by the user.
    try:
        with destination.open("x", encoding="utf-8") as output:
            output.write("\n".join(result) + "\n")
    except FileExistsError:
        pass
    if os.name != "nt":
        destination.chmod(0o600)
    return destination


def missing_credentials(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if separator:
            values[name.strip()] = value.strip().strip("\"'")
    required = ["DATABASE_URL", "OPENAI_API_KEY", "AUTH_SESSION_SECRET", "PLATFORM_SERVICE_TOKEN"]
    if values.get("DEMO_LLM_PROVIDER") == "groq":
        required.append("GROQ_API_KEY")
    return [name for name in required if not values.get(name) or
            values[name].lower().startswith(("replace-", "your-", "your_", "[your"))]


def node_supported(version):
    match = re.match(r"v?(\d+)\.(\d+)", version)
    if not match:
        return False
    major, minor = map(int, match.groups())
    return (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22


def dependency_stamp(root):
    digest = hashlib.sha256(sys.implementation.cache_tag.encode())
    for name in DEPENDENCIES:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def run(command, cwd):
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-only", action="store_true", help="create .env and list missing fields without installing")
    parser.add_argument("--start", action="store_true", help="start after setup when all credentials are filled")
    args = parser.parse_args()
    path = prepare_env(ROOT)
    print("Credentials file: " + path.as_posix(), flush=True)
    print("Existing .env files are preserved; secret values are never printed.", flush=True)
    if not args.env_only:
        if not (3, 11) <= sys.version_info[:2] <= (3, 13):
            raise SystemExit("Install Python 3.12 (or 3.11-3.13), then rerun this file.")
        node = shutil.which("node")
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not node or not npm:
            raise SystemExit("Install Node.js LTS from https://nodejs.org/, reopen the terminal, and rerun.")
        version = subprocess.check_output([node, "--version"], text=True).strip()
        if not node_supported(version):
            raise SystemExit("Node.js 20.19+, 22.12+, or a newer LTS version is required.")
        environment = ROOT / ".venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.exists():
            print("Creating the Python environment...", flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        stamp = environment / "demo-setup.json"
        expected = dependency_stamp(ROOT)
        try:
            installed = json.loads(stamp.read_text()).get("dependencies") == expected
        except (OSError, ValueError):
            installed = False
        if not installed or not (ROOT / "platform_frontend/node_modules").is_dir():
            print("Installing Python and frontend dependencies...", flush=True)
            run([python, "-m", "pip", "install", "--upgrade", "pip"], ROOT)
            run([python, "-m", "pip", "install", "-r", "requirements.txt", "-r",
                 "adaptive-learning-app/backend/requirements.txt"], ROOT)
            run([npm, "ci"], ROOT / "platform_frontend")
            stamp.write_text(json.dumps({"dependencies": expected}))
        print("Building the interface...", flush=True)
        run([npm, "run", "build"], ROOT / "platform_frontend")
    missing = missing_credentials(path)
    if missing:
        print("Fill these fields locally: " + ", ".join(missing), flush=True)
        print("Then rerun: python demo_mode.py --start", flush=True)
        return 2 if args.start else 0
    print("Configuration fields are filled. Credentials have not been transmitted or validated.", flush=True)
    if args.start and not args.env_only:
        return subprocess.call([str(python), "scripts/run_demo.py"], cwd=ROOT)
    print("Ready to start: python demo_mode.py --start", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError:
        raise SystemExit("A setup step failed. Fix the error above and rerun; .env is preserved.")
