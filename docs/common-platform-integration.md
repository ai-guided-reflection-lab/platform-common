# Common platform integration

## Local test run

Start Docker Desktop and make sure the local PostgreSQL test container is running. From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\run_wiring_test.py
```

Open `http://127.0.0.1:8015/platform/`. The launcher prints two disposable test logins and starts the platform, SDL bridge, and Reflections adapter. Use `Ctrl+C` in that terminal to stop the services. The test launcher uses a local-only database and separate test schemas. It does not connect to Supabase. Live AI is opt-in with `WIRING_ENABLE_LIVE_AI=true`; the updated OpenAI key was verified successfully on October 16, 2026. See `integration-test-status.md` for current results and remaining checks.

## UI and adapter boundaries

- `platform_frontend/src/workspace/` contains the platform workspace. `Workspace.jsx` owns sign-in, route selection, and shared page context.
- `StudentPages.jsx`, `InstructorStudio.jsx`, `DocumentLibrary.jsx`, `AssignmentDetails.jsx`, and `SupportingPages.jsx` render screens. Keep service calls out of these presentation components where practical.
- `service.js` maps platform API data into UI models and owns workspace/course/activity/file API calls.
- `platform_app/workspace.py` owns course codes, membership, course documents, the shared RAG API, and SDL synchronization.
- `platform_app/engines.py` adapts platform assignments to Socratic, Reflections, Debate, and SDL. Chat-specific UI and engines remain independently replaceable.

To restyle a screen, edit its workspace component or CSS. To change persistence or an engine connection, edit `service.js` or the corresponding platform adapter. This keeps visual changes from changing chat storage contracts.

## Supabase setup status

The local wiring run does not apply or alter Supabase migrations. Pointing the platform at Supabase requires a valid project connection string in `DATABASE_URL`, a strong `AUTH_SESSION_SECRET`, and a different strong `PLATFORM_SERVICE_TOKEN`. Keep those server-side. The platform and each chat use separate PostgreSQL schemas and initialize their schema migrations when their services start. Start the platform, Socratic, Reflections, and SDL services against the same Supabase database only after reviewing the migration SQL and confirming the project is intended for a fresh schema. Do not run the disposable local test launcher with the Supabase URL.

The updated AI key passed live embedding and chat checks. Shared RAG tables have been migrated in Supabase with existing records preserved. The integrated application still needs a complete Supabase-backed journey check; the local test launcher intentionally remains local-only.
