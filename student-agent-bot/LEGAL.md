# Legal & deployment information

This document is for instructors, IT staff, and institutional review.

## What this repository is

**SE Tutor Chat** (`student-agent-bot`) is a **student-built** web application for
undergraduate software-engineering tutoring. It provides:

- A browser UI for topic-based tutoring
- Built-in lesson topics (use cases, requirements, UML, agile)
- Optional professor topic authoring (Firecrawl + LLM draft)
- Simulated student replies for testing

**License:** [MIT](LICENSE) — you may deploy, modify, and use this code in a
college setting subject to the MIT terms.

**Author:** Rahul (`rahulrb99`)

## What this repository is not

This repo does **not** include the separate **LangGraph multi-agent tutor**
(teacher / Feynman / quiz agents with LangSmith Studio). That system is based on
third-party code:

- Upstream: [ghdkim/tutor-agent](https://github.com/ghdkim/tutor-agent)
- Upstream status: public on GitHub, **no LICENSE file** as of 2026
- Use of that component for institutional deployment should include **attribution**
  and, for anything beyond classroom demo, **permission from the upstream author**

## External services (paid APIs)

| Service | Purpose | Data sent |
|---------|---------|-----------|
| **OpenAI** and/or **Groq** | Tutor and student-simulation chat | Student messages, lesson prompts |
| **Firecrawl** | Link discovery for custom topics (optional) | Topic name, search queries |
| **Railway** (or other host) | Hosting | HTTP traffic only |

API keys are set as **environment variables** on the host. They must not be
committed to git.

## Student privacy (FERPA / institutional policy)

- Chat text is sent to the chosen LLM provider (OpenAI or Groq) for processing.
- Sessions are held **in server memory** by default; they are lost on restart.
- Transcripts may be stored in the **user's browser** (localStorage) only.
- Custom topics saved on the server filesystem may be **ephemeral** on cloud hosts
  that do not provide persistent disks.

**Recommendation for college deployment:**

1. Confirm with IT/legal that sending anonymized tutoring prompts to OpenAI/Groq
   is acceptable under your institution's policy.
2. Do not require students to enter real names or student IDs in chat.
3. Publish a short syllabus notice that AI tutoring is experimental and may be
   inaccurate.

## Deployment options

| Option | Notes |
|--------|--------|
| **Railway / Render** | Fastest; set env vars; generate public URL |
| **College VM / cloud** | `pip install -r requirements.txt` then `uvicorn app:app --host 0.0.0.0 --port $PORT` |
| **Behind campus VPN** | Recommended if the app should not be public internet |

See [README.md](README.md) for setup steps.

## Disclaimer

This application is for **educational practice**. AI-generated explanations may
contain errors. It is not a substitute for course materials, grading, or
instructor review.

## Third-party open-source libraries

This app uses standard Python packages (FastAPI, LangChain, Firecrawl client,
etc.) under permissive licenses (MIT, Apache-2.0). See `requirements.txt` and
each package's license on PyPI.
