"""Single public entry point. Run with: uvicorn platform_app.main:app."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "Socratic-Chat/backend"))

from app import settings  # noqa: E402
from app.main import app  # noqa: E402
from platform_app import store  # noqa: E402
from platform_app.routes import router  # noqa: E402

# Preserve existing authentication, administration, courses, and document APIs.
# Register the platform routes before the legacy frontend's catch-all mount.
legacy_frontend = app.router.routes.pop()
app.title = "ClubALL Learning Platform"
app.include_router(router)


@app.on_event("startup")
def initialize_platform():
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required by the shared platform.")
    if not settings.AUTH_SESSION_SECRET or not os.getenv("PLATFORM_SERVICE_TOKEN"):
        raise RuntimeError("Set AUTH_SESSION_SECRET and PLATFORM_SERVICE_TOKEN before starting the shared platform.")
    store.migrate()


@app.middleware("http")
async def platform_security(request, call_next):
    if request.headers.get("x-user-id"):
        return JSONResponse({"detail": "Use a signed login session."}, status_code=401)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/config.js", include_in_schema=False)
def frontend_config():
    return Response('window.SOCRATIC_CONFIG = {API_BASE_URL: "", PLATFORM_URL: "/platform/"};', media_type="application/javascript")


DIST = ROOT / "platform_frontend/dist"
if (DIST / "assets").exists():
    app.mount("/platform/assets", StaticFiles(directory=DIST / "assets"), name="platform-assets")


@app.get("/platform", include_in_schema=False)
@app.get("/platform/{path:path}", include_in_schema=False)
def frontend(path: str = ""):
    page = DIST / ("reflections.html" if path == "reflections.html" else "index.html")
    if not page.exists():
        return Response("Build the platform frontend: cd platform_frontend && npm install && npm run build", status_code=503)
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


app.router.routes.append(legacy_frontend)
