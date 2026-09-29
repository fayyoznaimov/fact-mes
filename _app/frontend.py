"""Изолированная раздача собранного интерфейса /next/. API и права — в web.py."""
from pathlib import Path
import re
import json
from urllib.parse import unquote

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
SHELL = Path(__file__).with_name("ui.html")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".woff2": "font/woff2", ".svg": "image/svg+xml"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")


def response(url_path):
    headers = {"Cache-Control": "no-cache", "Content-Security-Policy": CSP,
               "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "same-origin"}
    if url_path == "/next":
        return 308, b"", "text/plain", {**headers, "Location": "/next/"}
    name = unquote(url_path.removeprefix("/next/")) or "index.html"
    if name != "index.html" and not re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(js|css|woff2|svg)", name):
        return 404, b"Not found", "text/plain", headers
    root = DIST.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        return 404, b"Not found", "text/plain", headers
    try:
        data = path.read_bytes()
        if name == "index.html":
            manifest = json.loads((root / ".vite" / "manifest.json").read_text(encoding="utf-8"))
            entry = manifest["index.html"]["file"]
            if not re.fullmatch(r"assets/[A-Za-z0-9_-]+\.js", entry):
                raise ValueError("invalid frontend entry")
            data = SHELL.read_bytes() + ('\n<script type="module" src="/next/' + entry + '"></script>\n').encode()
    except FileNotFoundError:
        if name == "index.html":
            return 503, "Новый интерфейс ещё не собран. Откройте основной адрес приложения.".encode(), "text/plain; charset=utf-8", headers
        return 404, b"Not found", "text/plain", headers
    return 200, data, TYPES[path.suffix], headers
