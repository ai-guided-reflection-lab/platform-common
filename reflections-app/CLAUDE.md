# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend
```bash
cd backend
source .venv/bin/activate          # Activate virtual env
uvicorn app.main:app --reload      # Run dev server (port 8000)
pip install -r requirements.txt    # Install dependencies
```

### Frontend
```bash
cd frontend
npm install                        # Install dependencies
npm run dev                        # Run dev server (port 5173)
npm run build                      # Production build
```

### Docker (full stack)
```bash
docker compose up --build          # Run all services (db:5432, backend:8000, frontend:3000)
docker compose down                # Stop all services
```

## Architecture

### Overview
Academic prototype — professors configure reflection modules, students chat with an LLM-powered bot, and transcripts are evaluated and stored for research analytics.

### Module Types
Two distinct module types drive different student flows:
- **`topic_based`** — conversational LLM chat with question-by-question reflection, timer, and evaluation
- **`milestone_based`** — student submits a free-text reflection; SCS finds top-k similar past students; optional LLM summary is shown

### Data Flow — Topic-Based
1. **Professor** creates a `Module` (`module_type=topic_based`) and configures it (`ModuleConfig`: topics, depth, probing style)
2. **Student** starts a chat session (`POST /api/chat/start`) → gets `session_id` + LLM greeting
3. Student exchanges messages (`POST /api/chat/message`) — in-memory session state in `chat_service.py`
4. Session ends (`POST /api/chat/end`) → transcript evaluated by LLM → persisted as `Conversation` + `ReflectionAnalytics`
5. **Dashboard** (`/api/analytics`) reads stored analytics

### Data Flow — Milestone-Based
1. **Professor** creates a `Module` (`module_type=milestone_based`), sets a `milestone_prompt`, and uploads a CSV of historical student challenges/solutions
2. **Student** reads the prompt, writes a free-text reflection, and submits (`POST /api/rec-sys/milestone`)
3. SCS computes cosine similarity (via `stsb-roberta-large`) against historical challenges → returns top-k matches
4. LLM generates an encouraging summary paragraph based on the student's reflection and the similar past experiences

### Backend (`backend/app/`)
- **`main.py`** — FastAPI app; tables are auto-created on startup via `Base.metadata.create_all()` (no migration system); registers routers: `modules`, `config`, `chat`, `analytics`, `rec_sys`
- **`models.py`** — SQLAlchemy models: `Student`, `Module` (with `module_type`), `ModuleConfig` (with `milestone_prompt` + `milestone_historical_data`), `Conversation`, `ReflectionAnalytics`
- **`services/chat_service.py`** — holds in-memory `{session_id: session_state}` dict; sessions are ephemeral (lost on restart)
- **`services/llm.py`** — factory `get_llm_provider()` selects provider via `LLM_PROVIDER` env var; supports `openai`, `groq`, `ollama`
- **`services/evaluation.py`** — calls LLM at session end to score the transcript against `ModuleConfig`
- **`services/prompts.py`** — system prompt templates; `build_reflection_prompt` drives a question-by-question flow: LLM asks one topic question at a time, acknowledges correct answers briefly, corrects misconceptions in 2–3 sentences, then moves on
- **`services/rec_sys_service.py`** — recommendation engine: `run_scs()` (cosine similarity via `sentence-transformers`), `run_llm_scs()` (SCS + personalized email per student), `generate_milestone_summary()` (student-facing paragraph)
- **`routes/rec_sys.py`** — two endpoints: `POST /api/rec-sys/run` (bulk CSV upload, SCS or LLM-SCS mode) and `POST /api/rec-sys/milestone` (single student milestone reflection)
- **`routes/`** — thin routers; business logic lives in `services/`

### Frontend (`frontend/src/`)
- Single-page app with React Router; three views: `/` (Chat), `/config` (ProfessorConfig), `/dashboard` (Dashboard)
- `Chat.jsx` handles both module types via a `phase` state machine: `setup → chatting → ended` (topic) or `setup → milestone → milestone_results` (milestone)
- All API calls use relative `/api/*` paths (Vite proxies to backend in dev, or served by the same origin in Docker)
- No state management library — local `useState`/`useEffect` only

### Environment Variables
Copy `backend/.env.example` to `backend/.env`. Key vars:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `LLM_PROVIDER` | `openai` \| `groq` \| `ollama` |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | API key for chosen provider |
| `OPENAI_MODEL` / `GROQ_MODEL` | Model name (e.g. `gpt-4o-mini`, `llama-3.3-70b-versatile`) |

`docker-compose.yml` currently hard-codes a Supabase `DATABASE_URL` and falls back to a placeholder `OPENAI_API_KEY`; override via shell env or a `.env` file at the repo root.

### Database
No migration framework — schema evolves by modifying `models.py`; tables are recreated on the next startup only if they don't exist. To apply model changes to an existing DB, drop and recreate the affected tables manually or drop the whole DB.

Key columns added since initial schema:
- `modules.module_type` — `"topic_based"` (default) | `"milestone_based"`
- `module_configs.milestone_prompt` — question text shown to student
- `module_configs.milestone_historical_data` — raw CSV stored as TEXT

### Known Issues
- `backend/requirements.txt` is incomplete (missing FastAPI, SQLAlchemy, `sentence-transformers`, etc.); the `.venv` holds the actual installed packages
- In-memory chat sessions are lost on backend restart
- `sentence-transformers` (`stsb-roberta-large`) is loaded lazily on first SCS request; first call will be slow while the model downloads (~300 MB)
