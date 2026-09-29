"""Local preview helper for the platform build at both / and /platform/."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


DIST = Path(__file__).resolve().parent / "dist"


class PlatformPreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = urlsplit(path).path
        if clean == "/":
            clean = "/index.html"
        elif clean.startswith("/platform/"):
            clean = clean.removeprefix("/platform")
        candidate = (DIST / clean.lstrip("/")).resolve()
        if not candidate.is_file() or not str(candidate).startswith(str(DIST.resolve())):
            candidate = DIST / "index.html"
        return str(candidate)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 5173), PlatformPreviewHandler).serve_forever()
