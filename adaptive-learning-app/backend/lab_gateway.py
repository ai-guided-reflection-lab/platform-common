"""Student-only public surface. Tunnel this server, never the authoring API."""
import os
import re
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
DIST = Path(__file__).resolve().parents[1] / "student-app/dist"
UPSTREAM = os.getenv("ADAPTIVE_LAB_API_URL", "http://127.0.0.1:8100").rstrip("/")
LESSON = r"/api/student/assignments/[^/]+"


def allowed(method, path):
    if (method, path) in {("POST", "/api/lab/sessions"), ("GET", "/api/lab/session"),
                          ("GET", "/api/student/assignments"), ("POST", "/api/lab/redeem")}:
        return True
    if method == "GET":
        return bool(re.fullmatch(LESSON + r"(?:/attempt)?", path))
    return method == "POST" and bool(re.fullmatch(
        LESSON + r"/(?:start|restart|learning-turn|study-complete|quiz|messages|submit-task)", path))


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def public_surface(path: str, request: Request):
    route = "/" + path
    if allowed(request.method, route):
        headers = {"Content-Type": "application/json"}
        if route != "/api/lab/sessions":
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse({"detail": "Enter your name to join the lab."}, status_code=401)
            headers["Authorization"] = auth
        body = await request.body()
        if len(body) > 128 * 1024:
            return JSONResponse({"detail": "Request is too large."}, status_code=413)
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                upstream = await client.request(request.method, UPSTREAM + route, headers=headers, content=body)
            return Response(upstream.content, status_code=upstream.status_code,
                            media_type="application/json", headers={"Cache-Control": "no-store"})
        except httpx.HTTPError:
            return JSONResponse({"detail": "The learning service is unavailable. Please retry."}, status_code=503)
    if request.method == "GET" and (route == "/" or route == "/index.html" or route.startswith("/assets/")):
        file = (DIST / ("index.html" if route == "/" else path)).resolve()
        if file.is_relative_to(DIST.resolve()) and file.is_file():
            return FileResponse(file)
    return JSONResponse({"detail": "Not found."}, status_code=404)
