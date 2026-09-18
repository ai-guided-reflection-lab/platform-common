"""FastAPI application entry point."""

import asyncio
import os
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.database import engine, Base
from app.routes import modules, config, chat, analytics, rec_sys, platform
from app.agents import runner as agent_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    max_retries = int(os.getenv("DB_STARTUP_MAX_RETRIES", "20"))
    retry_delay_seconds = float(os.getenv("DB_STARTUP_RETRY_DELAY_SECONDS", "1"))

    # Retry DB initialization to tolerate container startup races.
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except OperationalError:
            if attempt == max_retries:
                raise
            await asyncio.sleep(retry_delay_seconds)

    # Set up LangGraph checkpointer tables and compile graphs.
    agent_runner.setup_checkpointer()
    yield
    agent_runner.teardown_checkpointer()


app = FastAPI(
    title="Reflection Chatbot API",
    description="Minimal academic prototype — AI-powered reflection chatbot",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(modules.router)
app.include_router(config.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(rec_sys.router)
app.include_router(platform.router)


@app.middleware("http")
async def service_auth(request: Request, call_next):
    secret = os.getenv("PLATFORM_SERVICE_TOKEN", "")
    internal = request.url.path.startswith("/internal/")
    if (secret and request.url.path != "/health") or internal:
        if not secret or not hmac.compare_digest(request.headers.get("x-platform-service", ""), secret):
            return JSONResponse({"detail": "Platform service authentication required."}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}
