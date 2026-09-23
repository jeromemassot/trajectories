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
from data_gen import make_population
from massive_gen import BatchGenerationJob, generate_preview_sample

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

        if route == "/api/generate/batch/status":
            self._send_json(BatchGenerationJob().get_status())
            return

        if route == "/api/dataset":
            self._send_json({"observations": OBSERVATIONS})
            return

        if route == "/api/export":
            body = json.dumps(OBSERVATIONS, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", 'attachment; filename="trajectories_observations.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
        global OBSERVATIONS, CANDIDATE_FEATURES
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON body"}, 400)
            return

        if parsed.path == "/api/resolve":
            threshold = float(body.get("threshold", 0.65))
            weights = body.get("weights") or {}
            use_persistent_tokens = bool(body.get("use_persistent_tokens", True))
            try:
                result = resolve(
                    OBSERVATIONS,
                    weights=weights,
                    threshold=threshold,
                    precomputed_features=CANDIDATE_FEATURES,
                    use_persistent_tokens=use_persistent_tokens,
                )
            except Exception as e:  # pragma: no cover - defensive for a live demo
                self._send_json({"error": str(e)}, 500)
                return
            self._send_json(result)
            return

        if parsed.path == "/api/generate":
            try:
                gen_params = {
                    "seed": int(body.get("seed", 42)),
                    "target_obs": int(body["target_obs"]) if body.get("target_obs") is not None else None,
                    "n_individuals": int(body["n_individuals"]) if body.get("n_individuals") is not None else None,
                    "obs_distribution": str(body.get("obs_distribution", "gaussian")),
                    "mean_obs_per_person": float(body.get("mean_obs_per_person", 10.0)),
                    "std_obs_per_person": float(body.get("std_obs_per_person", 3.5)),
                    "min_obs_per_person": int(body.get("min_obs_per_person", 2)),
                    "max_obs_per_person": int(body.get("max_obs_per_person", 80)),
                    "pct_never_moved": float(body["pct_never_moved"]) if body.get("pct_never_moved") is not None else None,
                    "pct_county_moved": float(body["pct_county_moved"]) if body.get("pct_county_moved") is not None else None,
                    "pct_state_moved": float(body["pct_state_moved"]) if body.get("pct_state_moved") is not None else None,
                    "pct_cross_us_moved": float(body["pct_cross_us_moved"]) if body.get("pct_cross_us_moved") is not None else None,
                    "mean_county_moves": float(body.get("mean_county_moves", 1.8)),
                    "std_county_moves": float(body.get("std_county_moves", 0.8)),
                    "mean_state_moves": float(body.get("mean_state_moves", 2.2)),
                    "std_state_moves": float(body.get("std_state_moves", 0.9)),
                    "mean_cross_moves": float(body.get("mean_cross_moves", 3.1)),
                    "std_cross_moves": float(body.get("std_cross_moves", 1.2)),
                    "pct_household": float(body.get("pct_household", 5.0)),
                    "pct_collision": float(body.get("pct_collision", 2.0)),
                    "n_neighborhood": int(body.get("n_neighborhood", 6)),
                    "n_intrastate": int(body.get("n_intrastate", 6)),
                    "n_interstate": int(body.get("n_interstate", 6)),
                    "n_household_pairs": int(body.get("n_household_pairs", 3)),
                    "n_name_collision_pairs": int(body.get("n_name_collision_pairs", 2)),
                    "include_phone_reallocation": bool(body.get("include_phone_reallocation", True)),
                    "enable_dob_noise": bool(body.get("enable_dob_noise", True)),
                    "rate_dob_year_only": float(body.get("rate_dob_year_only", 0.10)),
                    "rate_dob_year_month": float(body.get("rate_dob_year_month", 0.10)),
                    "rate_dob_shift": float(body.get("rate_dob_shift", 0.12)),
                    "drop_dob_rate": float(body.get("drop_dob_rate", 0.12)),
                    "enable_name_noise": bool(body.get("enable_name_noise", True)),
                    "rate_first_noise": float(body.get("rate_first_noise", 0.35)),
                    "rate_last_noise": float(body.get("rate_last_noise", 0.15)),
                    "drop_address_rate": float(body.get("drop_address_rate", 0.10)),
                    "drop_email_rate": float(body.get("drop_email_rate", 0.08)),
                    "drop_phone_rate": float(body.get("drop_phone_rate", 0.08)),
                    "token_rate": float(body.get("token_rate", 0.60)),
                    "employer_rate": float(body.get("employer_rate", 0.70)),
                    "gender": str(body.get("gender", "both")).strip().lower(),
                    "return_summary": True,
                }
                new_obs, summary = make_population(**gen_params)
                OBSERVATIONS = new_obs
                CANDIDATE_FEATURES = extract_all_candidate_features(OBSERVATIONS)

                # Save to disk only if explicitly requested (defaults to False)
                if body.get("save_to_disk", False):
                    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(DATA_PATH, "w") as f:
                        json.dump(OBSERVATIONS, f, indent=2)

                threshold = float(body.get("threshold", 0.65))
                weights = body.get("weights") or {}
                use_persistent_tokens = bool(body.get("use_persistent_tokens", True))
                result = resolve(
                    OBSERVATIONS,
                    weights=weights,
                    threshold=threshold,
                    precomputed_features=CANDIDATE_FEATURES,
                    use_persistent_tokens=use_persistent_tokens,
                )
                self._send_json({
                    "status": "ok",
                    "observations": OBSERVATIONS,
                    "summary": summary,
                    "result": result,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if parsed.path == "/api/generate/batch":
            try:
                out_path = body.get("output_path") or str(BACKEND_DIR / "data" / "massive_dataset.jsonl")
                out_p = Path(out_path).resolve()
                ok, msg = BatchGenerationJob().start(body, out_p)
                if ok:
                    self._send_json({"status": "ok", "job_id": msg, "output_path": str(out_p)})
                else:
                    self._send_json({"error": msg}, 400)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if parsed.path == "/api/generate/batch/cancel":
            cancelled = BatchGenerationJob().cancel()
            self._send_json({"status": "ok", "cancelled": cancelled})
            return

        if parsed.path == "/api/generate/preview":
            try:
                target_preview_obs = int(body.get("target_preview_obs", 400))
                new_obs, summary = generate_preview_sample(body, target_obs=target_preview_obs)
                OBSERVATIONS = new_obs
                CANDIDATE_FEATURES = extract_all_candidate_features(OBSERVATIONS)
                threshold = float(body.get("threshold", 0.65))
                weights = body.get("weights") or {}
                use_persistent_tokens = bool(body.get("use_persistent_tokens", True))
                result = resolve(
                    OBSERVATIONS,
                    weights=weights,
                    threshold=threshold,
                    precomputed_features=CANDIDATE_FEATURES,
                    use_persistent_tokens=use_persistent_tokens,
                )
                self._send_json({
                    "status": "ok",
                    "observations": OBSERVATIONS,
                    "summary": summary,
                    "result": result,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"error": "not found"}, 404)


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
