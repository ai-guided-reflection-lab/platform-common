# Reflections Chatbot

An AI-powered reflection chatbot for academic use. Professors configure modules with learning topics; students chat with an LLM that guides reflection, and transcripts are evaluated and stored for analytics.

## Prerequisites

- Python 3.10+ with a virtual environment
- Node.js 18+
- A Supabase project (or local PostgreSQL via Docker)

### Node.js
Can be downloaded at https://nodejs.org/en/download

### Supabase
Can be downloaded at https://supabase.com/docs/guides/local-development/cli/getting-started

Use these commands to create Docker images.

```
supabase init
supabase start
```

Afterwards, just run `supabase start` to start it up again.
Run `supabase stop` to stop it when done.

## Backend

```bash
cd backend
python3 -m venv venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. Tables are created automatically on first startup.

**Environment setup** — 

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `LLM_PROVIDER` | `openai` \| `groq` \| `ollama` |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | API key for the chosen provider |
| `OPENAI_MODEL` / `GROQ_MODEL` | Model name (e.g. `gpt-4o-mini`, `llama-3.3-70b-versatile`) |

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:5173`. Vite proxies all `/api/*` requests to the backend at `http://localhost:8000`, so both servers must be running simultaneously.

## Routes

| Path | View |
|---|---|
| `/` | Student chat interface |
| `/config` | Professor module configuration |
| `/dashboard` | Analytics dashboard |

## Docker (alternative)

```bash
docker compose up --build
```

Starts the backend on `8000` and frontend on `3000`, using the `DATABASE_URL` from the project `.env`.
