"""Offline boundary checks against the actual PR installation (no model calls)."""

import json

import pytest
from test_evaluation import artifact

from asago_demo.evaluation import EvaluationDeadline, build_conversation


def test_pr_probe_preserves_transcript_through_openai_serializer(tmp_path, monkeypatch):
    pytest.importorskip("garak")
    for name in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name))
    from garak import _config
    from garak.generators.openai import OpenAICompatible
    from garak.probes.injection import IndirectInjection

    _config.load_base_config()
    entry = build_conversation(artifact())
    source = tmp_path / "conversation.json"
    source.write_text(json.dumps(entry))
    probe = IndirectInjection(
        config_root={
            "probes": {
                "injection": {
                    "IndirectInjection": {
                        "conversation_source": str(source),
                        "generations": 1,
                    }
                }
            }
        }
    )
    attempt = probe._mint_attempt(probe.prompts[0], seq=0)
    assert OpenAICompatible._conversation_to_list(attempt.prompt) == entry["messages"]
    assert attempt.prompt.notes["tools"] == entry["tools"]
    assert attempt.prompt.notes["judge_description"] == entry["judge_description"]


def test_deadline_cannot_be_wrapped_as_retryable_sdk_error():
    httpx = pytest.importorskip("httpx")
    openai = pytest.importorskip("openai")

    def transport(_request):
        raise EvaluationDeadline("deadline")

    client = openai.OpenAI(
        api_key="offline-test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    with pytest.raises(EvaluationDeadline):
        client.chat.completions.create(
            model="offline",
            messages=[
                {
                    "role": "user",
                    "content": "test",
                }
            ],
        )
    client.close()


def test_evaluation_routes_target_and_judge_to_separate_services(tmp_path, monkeypatch):
    pytest.importorskip("garak")
    from garak.harnesses.base import Harness

    from asago_demo.evaluation import evaluation

    (tmp_path / "source.json").write_text(json.dumps(artifact()))
    (tmp_path / "artifact.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "validation": {"ok": True},
                "file": "source.json",
                "scenario_id": "offline-scenario",
            }
        )
    )
    observed = []

    def inspect_clients(_self, target, _probes, detectors, _evaluator):
        judge = detectors[0].evaluation_generator
        observed.extend(
            [
                (str(target.client.base_url), target.client.api_key, target.name),
                (str(judge.client.base_url), judge.client.api_key, judge.name),
            ]
        )
        raise EvaluationDeadline("Offline boundary check; no model request")

    monkeypatch.setattr(Harness, "run", inspect_clients)
    result = evaluation(
        tmp_path,
        {
            "base_url": "https://proxy.example/v1",
            "api_key": "proxy-secret",
            "model": "gemma",
            "target_provider": "litellm",
            "target_model": "remote-target",
            "judge_provider": "ollama",
            "judge_model": "local-judge",
            "ollama_base_url": "http://localhost:11434",
        },
    )
    assert observed == [
        ("https://proxy.example/v1/", "proxy-secret", "remote-target"),
        ("http://localhost:11434/v1/", "ollama", "local-judge"),
    ]
    assert result["target_provider"] == "litellm"
    assert result["judge_model"] == "local-judge"


@pytest.mark.parametrize("provider", ["google", "ollama"])
def test_provider_request_parameters_and_errors(tmp_path, monkeypatch, provider):
    pytest.importorskip("garak")
    import httpx
    from garak import _config
    from garak.generators.openai import OpenAICompatible

    from asago_demo.evaluation import configure_generator, generator_options

    for name in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name))
    _config.load_base_config()
    _config.run.seed = 42
    connection = {
        "provider": provider,
        "model": "test-model",
        "base_url": "https://model.example/v1",
        "api_key": "test-key",
    }
    generator = OpenAICompatible(
        name="test-model",
        config_root={
            "generators": {"openai": {"OpenAICompatible": generator_options(connection)}}
        },
    )
    seen = []

    def transport(request):
        seen.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "model does not support tools"}})

    generator.client._client = httpx.Client(transport=httpx.MockTransport(transport))
    configure_generator(generator, connection, "Target", 120)
    with pytest.raises(ValueError, match="Target.*does not support tools"):
        generator._call_model(build_conversation(artifact())["messages"])
    assert ("frequency_penalty" in seen[0]) is (provider != "google")
    assert ("stop" in seen[0]) is (provider != "google")
    assert ("seed" in seen[0]) is (provider != "google")
    assert seen[0]["messages"] == build_conversation(artifact())["messages"]
    generator.client.close()
