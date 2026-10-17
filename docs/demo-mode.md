# Self-service demo

For a fresh checkout, ask Codex: **"Follow `demo_mode.md` to set up the demo, and open `.env` for me to add credentials."** Or run `python demo_mode.py` yourself from the repository root. It installs project dependencies, builds the interface, generates the session/service secrets, and prints the `.env` path and missing credential names. After filling credentials, run `python demo_mode.py --start`. Python and Node.js must be installed first; the full Codex instructions cover those prerequisites. Existing `.env` values are never overwritten.

Build the production frontend, then start the demo from the repository root:

```powershell
cd platform_frontend
npm run build
cd ..
.\.venv\Scripts\python.exe scripts\run_demo.py
```

Open `http://127.0.0.1:8015/platform/`. Enter any nonempty username and password. No invitation, email verification, or approval is required. The same combination returns to the same profile. A different combination creates a separate profile, including the same username with a different password. Usernames ignore case and surrounding whitespace; passwords are exact. Remember the combination: a typo creates a fresh profile rather than restoring the old one.

Each profile owns a linked instructor and student identity. The header toggle switches only between those two identities. Instructors see their own courses; students join courses deliberately by course code, including courses created by another tester. No role is granted to an existing normal account. Profile credentials are salted and hashed, never stored in plain text. Normal sign-in stays available when demo mode is disabled.

The launcher uses the root `.env` database and persistent `demo_platform`, `demo_socratic`, `demo_shared_rag`, `demo_sdl`, and `demo_reflections` schemas. Keep `DATABASE_URL`, `AUTH_SESSION_SECRET`, and `PLATFORM_SERVICE_TOKEN` configured server-side. Stopping and restarting the launcher preserves profiles and their work. It starts the platform on 8015 and SDL on 8115. OpenAI is the default demo provider; `DEMO_LLM_PROVIDER` can override it. Reflections requires its separate service to be configured with the same demo schema and service token; this launcher does not start that service.

For another deployment, explicitly set `PLATFORM_DEMO_MODE=true` and configure all five schema variables to names beginning with `demo_`. Otherwise the demo creation and switching endpoints return 404. Leave demo mode disabled on the Canvas/production deployment. Anonymous shared-persona sign-in is no longer automatically attempted by the interface.
