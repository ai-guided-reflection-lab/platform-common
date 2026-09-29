FROM node:22-bookworm-slim AS frontend
WORKDIR /build/platform_frontend
COPY platform_frontend/package*.json ./
RUN npm ci
COPY platform_frontend/ ./
COPY reflections-app/frontend/src/ /build/reflections-app/frontend/src/
RUN npm run build

FROM python:3.12-slim
WORKDIR /workspace
RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
COPY Socratic-Chat/backend/requirements.txt Socratic-Chat/backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY platform_app/ platform_app/
COPY scripts/ scripts/
COPY Socratic-Chat/backend/app/ Socratic-Chat/backend/app/
COPY Socratic-Chat/frontend/ Socratic-Chat/frontend/
COPY student-agent-bot/data/topics/builtin/ student-agent-bot/data/topics/builtin/
COPY --from=frontend /build/platform_frontend/dist/ platform_frontend/dist/
RUN mkdir -p Socratic-Chat/backend/storage Socratic-Chat/backend/data/raw_docs
CMD ["uvicorn", "platform_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
