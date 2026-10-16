# Codex: set up this demo

Use this repository's existing branch and working directory. Do not copy credentials from another checkout.

1. Check for Python 3.11-3.13 (3.12 recommended) and Node.js LTS (20.19+ or 22.12+). If missing, help install them from their official sources and reopen the terminal as needed. The setup script installs project dependencies, not these system runtimes.
2. From the repository root run `python demo_mode.py`. It creates `.venv`, installs the platform and SDL Python dependencies, runs `npm ci`, builds the interface, and creates a Git-ignored `.env` only if one does not already exist. It generates independent session/service secrets automatically.
3. Open the root `.env` in the editor and provide the user a clickable link to its absolute path. Show only missing variable names; never display the file contents or secret values. Ask the user to fill `DATABASE_URL` with an authorized PostgreSQL/Supabase connection and `OPENAI_API_KEY` locally. Groq also needs `GROQ_API_KEY` if selected. No database is provisioned automatically.
4. Wait for the user to confirm credentials are saved. Run `python demo_mode.py --start`. Previously installed dependencies are reused when the requirements have not changed. Do not commit `.env`, `.venv`, or generated files.
5. Open `http://127.0.0.1:8015/platform/`. Any username/password combination creates or restores a demo profile with both Student and Professor roles. See `docs/demo-mode.md` for isolation and service details.

Do not claim all chatbot services are running: the launcher starts the common platform and SDL. Reflections requires its separately configured backend. First-time PDF ingestion may download model assets.

For configuration-file creation without dependency installation: `python demo_mode.py --env-only`.
