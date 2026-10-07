import pytest

from asago_demo.notebook_client import DemoClient


def test_cell_finishes_its_stage_even_if_another_stage_is_running(monkeypatch):
    client = DemoClient()
    responses = iter(
        [
            {"run_id": "A"},
            {
                "busy": True,
                "active_id": "B",
                "run": {
                    "status": "completed",
                    "stages": {"policy": {"status": "completed"}},
                    "results": {"policy": {"count": 49}},
                },
            },
        ]
    )
    monkeypatch.setattr(client, "request", lambda *args: next(responses))
    assert client.run("policy") == {"count": 49}


def test_interrupt_only_cancels_the_requested_run_and_stage(monkeypatch):
    client = DemoClient()
    calls = []

    def request(route, data=None):
        calls.append((route, data))
        if route == "/api/start":
            return {"run_id": "A"}
        if route.startswith("/api/state"):
            raise KeyboardInterrupt
        return {"ok": True}

    monkeypatch.setattr(client, "request", request)
    with pytest.raises(KeyboardInterrupt):
        client.run("policy")
    assert calls[-1] == ("/api/cancel", {"run": "A", "stage": "policy"})
