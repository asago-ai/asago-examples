import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from asago_demo.runtime import Coordinator, Settings
from asago_demo.server import make_handler


@pytest.fixture
def server(tmp_path):
    coordinator = Coordinator(
        tmp_path,
        Settings(
            tmp_path, defaults={"api_key": "secret-value", "google_api_key": "google-saved-secret"}
        ),
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(coordinator))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", coordinator
    httpd.shutdown()
    httpd.server_close()


def test_saved_demo_api_preserves_evidence_and_rejects_execution(server):
    from test_snapshots import saved_run

    base, coordinator = server
    saved_run(coordinator.root)
    with urllib.request.urlopen(base + "/api/state?run=saved") as response:
        state = json.load(response)
    assert state["run"]["read_only"] is True
    assert state["run"]["snapshot"]["source_run_id"] == "original"
    with urllib.request.urlopen(base + "/files/saved/policy/report.html") as response:
        assert response.read() == b"Original report"
    request = urllib.request.Request(
        base + "/api/start",
        data=json.dumps({"run": "saved", "stage": "all"}).encode(),
        headers={"X-Asago-Demo": "1", "Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 400
    assert "read-only" in json.load(error.value)["error"]
    assert not coordinator.busy


def test_status_does_not_disclose_secrets(server):
    base, _ = server
    with urllib.request.urlopen(base + "/api/state") as response:
        data = response.read().decode()
    assert "secret-value" not in data
    assert "google-saved-secret" not in data
    assert json.loads(data)["settings"]["google_api_key_configured"]
    assert json.loads(data)["settings"]["api_key_configured"]


def test_snapshot_creation_endpoint_is_unavailable(server):
    base, coordinator = server
    request = urllib.request.Request(
        base + "/api/snapshots",
        data=b"{}",
        headers={"X-Asago-Demo": "1", "Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 404
    assert list(coordinator.runs.iterdir()) == []


def test_browser_requests_cannot_start_jobs_cross_origin(server):
    base, _ = server
    request = urllib.request.Request(
        base + "/api/start",
        data=b'{"stage":"policy"}',
        headers={
            "Origin": "https://unrelated.example",
            "X-Asago-Demo": "1",
        },
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 403


def test_html_outputs_are_sandboxed_and_traversal_blocked(server):
    base, coordinator = server
    (coordinator.runs / "test.html").write_text("<script>fetch('/api/state')</script>")
    with urllib.request.urlopen(base + "/files/test.html") as response:
        assert "connect-src 'none'" in response.headers["Content-Security-Policy"]
        assert "allow-same-origin" not in response.headers["Content-Security-Policy"]
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(base + "/files/../settings.json")


def test_only_policy_report_can_open_its_pdf_outside_the_sandbox(server):
    base, coordinator = server
    policy = coordinator.runs / "test-run" / "policy"
    policy.mkdir(parents=True)
    (policy / "report.html").write_text("<h1>Saved policy</h1>")
    import pypdfium2 as pdfium

    with pdfium.PdfDocument.new() as document:
        document.new_page(100, 100).close()
        document.save(policy / "policy.pdf")
    other = coordinator.runs / "test-run" / "report.html"
    other.write_text("<h1>Generated report</h1>")
    for route, can_open in [("policy/report.html", True), ("report.html", False)]:
        with urllib.request.urlopen(base + "/files/test-run/" + route) as response:
            csp = response.headers["Content-Security-Policy"]
        assert ("allow-popups-to-escape-sandbox" in csp) is can_open
        assert "allow-same-origin" not in csp
        assert "connect-src 'none'" in csp
    with urllib.request.urlopen(base + "/files/test-run/policy/policy.pdf") as response:
        assert response.headers["Content-Type"] == "application/pdf"
        assert response.read().startswith(b"%PDF-")
    with urllib.request.urlopen(base + "/files/test-run/policy/document.html") as response:
        preview = response.read().decode()
        assert 'alt="Original policy PDF, page 1"' in preview
        assert 'href="policy.pdf" download="fs-isac.pdf"' in preview


@pytest.mark.parametrize(
    "provider,url,key",
    [
        ("litellm", "https://proxy.example/v1", "secret-value"),
        ("ollama", "http://localhost:11434", "ollama"),
    ],
)
def test_model_discovery_uses_draft_service_without_saving(
    server, monkeypatch, provider, url, key
):
    import httpx

    base, coordinator = server
    seen = []

    def models(request):
        seen.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(
            200, json={"data": [{"id": "qwen"}, {"id": "gemma"}, {"id": "qwen"}]}
        )

    with httpx.Client(transport=httpx.MockTransport(models)) as client:
        monkeypatch.setattr(httpx, "get", client.get)
        request = urllib.request.Request(
            base + "/api/models",
            data=json.dumps(
                {
                    "provider": provider,
                    "base_url": url,
                    "api_key": "",
                }
            ).encode(),
            headers={"X-Asago-Demo": "1"},
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)
    assert result["models"] == ["gemma", "qwen"]
    assert seen == [
        (url.rstrip("/") + ("/v1" if provider == "ollama" else "") + "/models", "Bearer " + key)
    ]
    assert not coordinator.settings.path.exists()


def test_google_discovery_keeps_draft_key_private_and_uses_google_only(server, monkeypatch):
    import httpx

    base, coordinator = server
    seen = []

    def models(request):
        seen.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(200, json={"data": [{"id": "models/gemini-flash-test"}]})

    with httpx.Client(transport=httpx.MockTransport(models)) as client:
        monkeypatch.setattr(httpx, "get", client.get)
        request = urllib.request.Request(
            base + "/api/models",
            data=json.dumps({"provider": "google", "api_key": "google-draft-secret"}).encode(),
            headers={"X-Asago-Demo": "1"},
        )
        with urllib.request.urlopen(request) as response:
            assert json.load(response)["models"] == ["gemini-flash-test"]
    assert seen == [
        (
            "https://generativelanguage.googleapis.com/v1beta/openai/models",
            "Bearer google-draft-secret",
        )
    ]
    assert not coordinator.settings.path.exists()


def test_google_discovery_error_redacts_unsaved_key(server, monkeypatch):
    import httpx

    base, _ = server

    def broken(*args, **kwargs):
        raise RuntimeError("Bad Google key: google-draft-secret")

    monkeypatch.setattr(httpx, "get", broken)
    request = urllib.request.Request(
        base + "/api/models",
        data=b'{"provider":"google","api_key":"google-draft-secret"}',
        headers={"X-Asago-Demo": "1"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert "google-draft-secret" not in error.value.read().decode()


def test_google_discovery_cannot_redirect_key_to_custom_url(server, monkeypatch):
    import httpx

    base, _ = server

    def unexpected_request(*args, **kwargs):
        pytest.fail("Google credentials must never go to a custom URL")

    monkeypatch.setattr(httpx, "get", unexpected_request)
    request = urllib.request.Request(
        base + "/api/models",
        data=b'{"provider":"google","base_url":"https://unrelated.example/v1","api_key":"google-draft-secret"}',
        headers={"X-Asago-Demo": "1"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert "official API endpoint" in error.value.read().decode()


def test_search_plan_endpoint_is_read_only(server):
    base, coordinator = server
    with urllib.request.urlopen(base + "/api/search-plan") as response:
        data = json.load(response)
    assert data["seed_count"] > 4
    assert data["input_count"] == 3
    assert data["model_calls"] == 0
    assert not coordinator.busy
    assert coordinator.history() == []
