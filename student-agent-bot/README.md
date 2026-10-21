# SE Tutor Chat

Undergraduate software-engineering tutoring web app (use cases, requirements, UML, agile).

**License:** [MIT](LICENSE) · **Legal / privacy / deployment:** [LEGAL.md](LEGAL.md)

> This repo is **original student work** for classroom deployment.  
> The separate LangGraph multi-agent tutor (LangSmith demo) is **third-party** — not included here.

## Topics

1. Use Case Diagrams
2. Software Requirements
3. UML Class Diagrams
4. Agile & Scrum Basics

## Flow

1. Pick model (Groq or OpenAI) and topic
2. Tutor sends W3Schools / GeeksforGeeks links — student reads and returns
3. Conceptual check questions
4. Guided practice (step-by-step)
5. Wrap-up and optional follow-up questions

## Local development

Create `.env` or set environment variables:

```env
GROQ_API_KEY=...
OPENAI_API_KEY=...
FIRECRAWL_API_KEY=...
```

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
```

Open **http://127.0.0.1:8080**

## Railway deployment

1. Connect this GitHub repo to [Railway](https://railway.app)
2. Set environment variables: `GROQ_API_KEY`, `OPENAI_API_KEY` (optional), `FIRECRAWL_API_KEY`
3. Generate a public domain (Settings → Networking)
4. Start command (from `railway.toml`): `uvicorn app:app --host 0.0.0.0 --port $PORT`

## Features

- Groq or OpenAI — chosen once per session
- Manual student replies or **Simulate student** button
- Professor **Manage topics** (Firecrawl + LLM draft)
- Session transcript download; browser resume via localStorage

## Session states

| State | What happens |
|-------|----------------|
| **Active** | Read → check → guided practice |
| **Complete** | Lesson done; follow-up questions |
| **Ended** | Chat locked; download or reset |

## Built-in vs custom topics

- **Built-in:** `data/topics/builtin/` (read-only, shipped with repo)
- **Custom:** `data/topics/custom/` (may not persist on ephemeral cloud disks)

## Privacy note

Chat messages are sent to OpenAI or Groq for processing. See [LEGAL.md](LEGAL.md) for FERPA/IT guidance.
