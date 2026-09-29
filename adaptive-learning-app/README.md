# Adaptive Learning — standalone Student Agent

This directory runs the Student Agent work independently from ClubALL, Socratic Chat, and Reflections. It contains two separate interfaces backed by one standalone API:

- Instructor studio: `http://127.0.0.1:5173`
- Student workspace: `http://127.0.0.1:5174`
- API documentation: `http://127.0.0.1:8100/docs`

## First-time setup

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r adaptive-learning-app\backend\requirements.txt
cd adaptive-learning-app\instructor-app
npm install
cd ..\student-app
npm install
```

The API reads the workspace root `.env`, so the existing `OPENAI_API_KEY` can be reused. Optional standalone overrides can be placed in `adaptive-learning-app/.env`; see `.env.example`.

## Run locally

Open three terminals:

```powershell
cd adaptive-learning-app\backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8100
```

```powershell
cd adaptive-learning-app\instructor-app
npm run dev
```

```powershell
cd adaptive-learning-app\student-app
npm run dev
```

After dependencies are installed, `adaptive-learning-app\start.ps1` starts all three processes.

## Demo flow

1. Open the instructor studio. A seeded published assignment is already available.
2. Choose **Quick setup**, enter a topic, and optionally attach a PDF, Markdown, or text course file. Demo students are selected automatically.
3. Select **Generate and publish assignment**. The app creates the objectives, publishes three trusted study links, prepares a five-question diagnostic, builds three levels of practice, indexes any attached material, and publishes the assignment.
4. Use **Advanced setup** only when you want to author the complete learning plan manually.
5. Open the student workspace and choose the assigned demo student.
6. Study the published resources and select **I'm ready for the quiz**.
7. Complete the five-question placement quiz. Scores `0–2` begin on the foundational path, `3` on standard, and `4–5` on accelerated.
8. Continue with free-response learning. The quiz selects the starting path but does not count as mastery; every objective still requires an independent demonstration.
9. Submit the required task, then return to the instructor studio to see study completion, quiz score, learning path, objective evidence, and completion.

Set `ADAPTIVE_AI_MODE=demo` to run without OpenAI calls. Demo mode uses deterministic local assessment and embeddings, which is also used by automated tests.

When `ADAPTIVE_AI_MODE=openai`, the service tries OpenAI first. If the configured key is rejected or OpenAI is temporarily unavailable, local presentations automatically continue in `demo-fallback` mode. Check `http://127.0.0.1:8100/api/health` to see the active mode. Set `ADAPTIVE_ALLOW_DEMO_FALLBACK=false` if an OpenAI failure should stop the request instead.

## Integration boundary

The standalone app owns its learning plans, tutoring flow, evidence, progress, and local RAG. Its current `X-Demo-User` identity and SQLite persistence are standalone adapters. A later ClubALL adapter can replace identity, course enrollment, assignments, and persistence while keeping the Student Agent workflow and both role-specific interfaces intact.

## Verification

```powershell
cd adaptive-learning-app\backend
..\..\.venv\Scripts\python.exe -m pytest tests -q

cd ..\instructor-app
npm run build

cd ..\student-app
npm run build
```
