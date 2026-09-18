FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY platform_frontend/package*.json ./
RUN npm ci
COPY platform_frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /workspace
COPY requirements.txt ./
COPY Socratic-Chat/backend/requirements.txt Socratic-Chat/backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY platform_app/ platform_app/
COPY scripts/ scripts/
COPY Socratic-Chat/backend/app/ Socratic-Chat/backend/app/
COPY Socratic-Chat/frontend/ Socratic-Chat/frontend/
COPY student-agent-bot/data/topics/builtin/ student-agent-bot/data/topics/builtin/
COPY --from=frontend /build/dist/ platform_frontend/dist/
RUN mkdir -p Socratic-Chat/backend/storage Socratic-Chat/backend/data/raw_docs
CMD ["uvicorn", "platform_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
