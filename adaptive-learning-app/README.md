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

After dependencies are installed, `adaptive-learning-app\start.ps1` starts all three processes using the local SQLite database by default. Pass `-UseConfiguredDatabase` to use the database configured in your environment instead.

## Demo flow

1. Open the student workspace and choose Alex or Jordan. The configured Requirements Engineering sample is available in a fresh local database.
2. Open a lesson for the personalized greeting, short introduction, concrete example, objectives, and one familiarity question.
3. Study the approved links, ask for examples or help, then select **I am done** or send a readiness reply.
4. Answer five MCQs, one at a time. Report confidence on each and explain questions 4 and 5. Missing details, hints, and “I don't know” are supported.
5. See the score out of five and a targeted follow-up. Work through fresh examples and independent checks; confidence does not change the quiz score.
6. Reflect on what you can do now, then choose another example, a challenge, a recap, or a pause. The session stays open and progress is saved.
7. The instructor studio shows the original diagnostic evidence, confidence, explanations, assistance, practice revisions, and reflections.

For a new topic, use **Advanced setup** to supply approved material, objectives, links with study focus, questions and keys, explanations, and practice rubrics. **Quick setup** requires the same source material and a configured AI provider; it creates a draft for professor review. Missing authoring information blocks publication instead of generating unsupported content. Published lessons are read-only.

Set `ADAPTIVE_AI_MODE=demo` for offline use. Local assessment follows explicit professor-authored phrase groups and is approximate. Live semantic assessment requires the configured provider. Set `ADAPTIVE_DATABASE_PATH` to the absolute local SQLite path if your workspace environment points to a remote database that is unavailable.

See [the exact student flow](docs/student-learning-flow.md) for stage behavior and assessment limits. The latest flow is version 2; existing version 1 lessons and student work remain intact.

## Integration boundary

The standalone app owns its learning plans, tutoring flow, evidence, progress, and local RAG. Its current `X-Demo-User` identity and SQLite persistence are standalone adapters. A later ClubALL adapter can replace identity, course enrollment, assignments, and persistence while keeping the Student Agent workflow and both role-specific interfaces intact.

## Verification

```powershell
cd adaptive-learning-app\backend
..\..\.venv\Scripts\python.exe -m pytest tests -q

cd ..\instructor-app
npm run build -- --configLoader runner

cd ..\student-app
npm run build -- --configLoader runner
```
