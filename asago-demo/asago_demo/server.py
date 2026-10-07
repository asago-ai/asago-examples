"""Local HTML interface and a narrow API for the demo stage runner."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
REPORT_TEMPLATES = ROOT / ".cache/policy-report/src/asago_policy_mapper/templates"
sys.path.insert(0, str(ROOT))

from asago_demo.runtime import (  # noqa: E402
    DEMO_PRESET,
    FULL_SEARCH_OPTIONS,
    SCENARIO_PRESETS,
    Coordinator,
    Settings,
    model_connection,
    provider_connection,
    redact_value,
    redacted_file,
    safe_child,
)


def make_handler(coordinator):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, body, content_type="application/json", code=200, extra=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self.valid_host():
                return self.send({"error": "Local requests only"}, code=403)
            parsed = urlparse(self.path)
            route = unquote(parsed.path)
            try:
                if route == "/api/state":
                    run_id = parse_qs(parsed.query).get("run", [None])[0]
                    state = coordinator.current(run_id)
                    if state:
                        state.pop("_path", None)
                    return self.send(
                        {
                            "run": state,
                            "history": coordinator.history(),
                            "busy": coordinator.busy,
                            "active_id": coordinator.active_id,
                            "settings": coordinator.settings.public(),
                            "demo_preset": DEMO_PRESET,
                            "scenario_presets": SCENARIO_PRESETS,
                            "full_search_options": FULL_SEARCH_OPTIONS,
                        }
                    )
                if route == "/api/search-plan":
                    from asago_demo.planning import full_search_plan

                    return self.send(full_search_plan())
                if route.startswith("/files/"):
                    path = safe_child(coordinator.runs, route.removeprefix("/files/"))
                    if path.suffix not in {
                        ".html",
                        ".json",
                        ".jsonl",
                        ".yaml",
                        ".yml",
                        ".feature",
                        ".pdf",
                        ".log",
                    }:
                        raise ValueError("Unsupported output file")
                    return self.file(path, report=True)
                if route == "/assets/logo.svg":
                    return self.file(REPORT_TEMPLATES / "assets/asago-main-logo-dark.svg")
                if route == "/assets/branding.css":
                    path = REPORT_TEMPLATES / "report_branding.html"
                    text = path.read_text()
                    css = text.split("<style>", 1)[1].split("</style>", 1)[0]
                    return self.send(css.encode(), "text/css")
                if route == "/assets/patternfly.css":
                    from asago_demo.reporting import report_module

                    css, _, _ = report_module()._browser_assets()
                    return self.send(css.encode(), "text/css")
                static = {
                    "/": "index.html",
                    "/app.js": "app.js",
                    "/style.css": "style.css",
                    "/view-state.js": "view-state.js",
                }
                if route in static:
                    return self.file(ROOT / static[route])
                return self.send({"error": "Not found"}, code=404)
            except (ValueError, FileNotFoundError) as exc:
                return self.send({"error": str(exc)}, code=404)

        def file(self, path, report=False):
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".js":
                mime = "text/javascript"
            headers = {}
            policy_report = (
                report
                and path.name == "report.html"
                and path.parent.name == "policy"
                and path.with_name("policy.pdf").is_file()
            )
            if report and path.suffix == ".html":
                # Exported model text/scripts cannot reach the local control API.
                sandbox = "sandbox allow-scripts allow-downloads"
                if policy_report:
                    # The linked PDF opens in its own viewer, outside this frame.
                    sandbox += " allow-popups allow-popups-to-escape-sandbox"
                headers["Content-Security-Policy"] = (
                    sandbox + "; "
                    "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; "
                    "style-src 'unsafe-inline'; font-src data:; img-src data:; "
                    "connect-src 'none'"
                )
            content = path.read_bytes()
            if report and path.suffix != ".pdf":
                content = redacted_file(path, coordinator.settings.private()).encode("utf-8")
            if policy_report:
                from asago_demo.reporting import build_policy_document, customize_policy_header

                build_policy_document(path.with_name("policy.pdf"))
                content = customize_policy_header(content.decode("utf-8")).encode("utf-8")
            return self.send(content, mime, extra=headers)

        def do_POST(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if (
                not self.valid_host()
                or self.headers.get("X-Asago-Demo") != "1"
                or (origin and origin != f"http://{host}")
            ):
                return self.send({"error": "Use the local demo page to start runs"}, code=403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 16384:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                if self.path == "/api/start":
                    run_id = coordinator.start(
                        data.get("stage", "all"), data.get("run"), data.get("scenario", "")
                    )
                    return self.send({"run_id": run_id})
                if self.path == "/api/cancel":
                    if not data.get("run"):
                        raise ValueError("Specify the run to stop")
                    stopped = coordinator.cancel(data["run"], data.get("stage"))
                    return self.send({"ok": stopped})
                if self.path == "/api/settings":
                    if coordinator.busy:
                        raise ValueError("Wait for the current run before changing settings")
                    coordinator.settings.update(data)
                    return self.send(coordinator.settings.public())
                if self.path == "/api/models":
                    import httpx

                    if set(data) - {"provider", "base_url", "api_key"}:
                        raise ValueError("Unknown model discovery field")
                    provider = data.get("provider")
                    if provider not in ("litellm", "ollama", "google"):
                        raise ValueError("Choose LiteLLM, Ollama or Google Gemini")
                    changes = {}
                    if provider == "google" and "base_url" in data:
                        raise ValueError("Google Gemini uses its official API endpoint")
                    if "base_url" in data:
                        changes["base_url" if provider == "litellm" else "ollama_base_url"] = data[
                            "base_url"
                        ]
                    if provider in {"litellm", "google"} and "api_key" in data:
                        changes["google_api_key" if provider == "google" else "api_key"] = data[
                            "api_key"
                        ]
                    settings = coordinator.settings.preview(changes)
                    connection = provider_connection(settings, provider)
                    if not connection["base_url"]:
                        raise ValueError("Enter the service URL before loading models")
                    try:
                        response = httpx.get(
                            connection["base_url"] + "/models",
                            headers={"Authorization": "Bearer " + connection["api_key"]},
                            timeout=20,
                        )
                        response.raise_for_status()
                        models = sorted(
                            {
                                entry["id"].removeprefix("models/")
                                if provider == "google"
                                else entry["id"]
                                for entry in response.json().get("data", [])
                                if isinstance(entry.get("id"), str)
                            }
                        )
                    except Exception as exc:
                        raise ValueError(redact_value(str(exc), settings)) from None
                    return self.send({"provider": provider, "models": models})
                if self.path in {"/api/check", "/api/check-target"}:
                    import httpx

                    settings = coordinator.settings.private()
                    target = self.path == "/api/check-target"
                    connection = model_connection(settings, "target" if target else "scenario")
                    response = httpx.get(
                        connection["base_url"] + "/models",
                        headers={"Authorization": "Bearer " + connection["api_key"]},
                        timeout=20,
                    )
                    response.raise_for_status()
                    models = [entry["id"] for entry in response.json().get("data", [])]
                    model = connection["model"]
                    return self.send({"models": models, "ready": model in models})
                return self.send({"error": "Not found"}, code=404)
            except Exception as exc:
                return self.send({"error": coordinator.redact(str(exc))}, code=400)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    coordinator = Coordinator(ROOT, Settings(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(coordinator))
    print(f"Asago demo ready: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
