"""
Minimal HTTP API + static file server for the Trajectories POC.

Deliberately implemented with only the Python standard library
(http.server + json) rather than FastAPI/Flask: this sandbox's network
egress is locked down and could not install third-party packages while
building this prototype, and shipping a zero-dependency server means the
demo runs anywhere `python3` exists, with no `pip install` step at all.

If you deploy this for real, swapping this file for a FastAPI app that
exposes the same three routes (GET /api/dataset, POST /api/resolve,
GET /api/health) is a ~30 minute change - resolution.py does not change
at all. See README.md.

Run:
    python3 server.py
Then open http://localhost:8000/ in a browser.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from resolution import resolve, extract_all_candidate_features

DATA_PATH = BACKEND_DIR / "data" / "mock_observations.json"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

with open(DATA_PATH) as f:
    OBSERVATIONS = json.load(f)

# Precompute candidate pair features once for instantaneous live re-resolution
CANDIDATE_FEATURES = extract_all_candidate_features(OBSERVATIONS)

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TrajectoriesPOC/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self._send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- routing ----------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/health":
            self._send_json({"status": "ok", "n_observations": len(OBSERVATIONS)})
            return

        if route == "/api/dataset":
            self._send_json({"observations": OBSERVATIONS})
            return

        # static frontend
        if route == "/":
            route = "/index.html"
        file_path = (FRONTEND_DIR / route.lstrip("/")).resolve()
        if FRONTEND_DIR.resolve() not in file_path.parents and file_path != FRONTEND_DIR.resolve():
            self._send_json({"error": "forbidden"}, 403)
            return
        ext = file_path.suffix
        content_type = MIME_TYPES.get(ext, "application/octet-stream")
        self._send_file(file_path, content_type)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/resolve":
            self._send_json({"error": "not found"}, 404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON body"}, 400)
            return

        threshold = float(body.get("threshold", 0.65))
        weights = body.get("weights") or {}
        try:
            result = resolve(
                OBSERVATIONS,
                weights=weights,
                threshold=threshold,
                precomputed_features=CANDIDATE_FEATURES,
            )
        except Exception as e:  # pragma: no cover - defensive for a live demo
            self._send_json({"error": str(e)}, 500)
            return
        self._send_json(result)


def main():
    port = 8000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Trajectories POC serving on http://localhost:{port}  "
          f"({len(OBSERVATIONS)} mock observations loaded)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
