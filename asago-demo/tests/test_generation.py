import pytest
from pydantic import ValidationError

from asago_demo.generation import generation_compatibility


def test_google_bounds_behavior_schema_without_changing_admission_contract():
    from asago_scenario_generator.pipeline.generate import behavior_semantics as behavior

    original = behavior.build_behavior_draft_response_model
    with generation_compatibility(provider="google", demo_preset=True):
        model = behavior.build_behavior_draft_response_model(["a0", "p0"], examples_allowed=False)
        schema = model.model_json_schema()
        assert schema["properties"]["scenarios"]["maxItems"] == 1
        assert schema["$defs"]["BehaviorScenarioDraft"]["properties"]["steps"]["maxItems"] == 2
        assert issubclass(model, behavior.BehaviorDraftV2)
        with pytest.raises(ValidationError):
            model.model_validate({"scenarios": [{"title": "bad", "steps": []}]})
    assert behavior.build_behavior_draft_response_model is original
    assert original(["a0", "p0"]).model_json_schema()["properties"]["scenarios"]["maxItems"] == 8


def test_actor_guidance_preserves_upstream_limits_and_inventory():
    from asago_scenario_generator.pipeline.generate import actor, actor_semantics

    choices = {
        "c0": ("external_attacker", "intermediate"),
        "c1": ("external_attacker", "advanced"),
    }
    with generation_compatibility(provider="google", demo_preset=True):
        prompt = actor._actor_draft_prompt(choices, {})
        assert "180 characters" in prompt
        assert "advanced" in prompt
        assert "c1" in prompt
        model = actor_semantics.create_actor_draft_v3_model(
            actor_choice_handles=tuple(choices), resource_handles=(), compact=False
        )
        schema = model.model_json_schema()
        assert schema["properties"]["intentions"]["items"]["maxLength"] == 200
        with pytest.raises(ValidationError):
            model.model_validate({"actor_choice_handle": "invented"})


def test_adapters_restore_even_when_pipeline_fails():
    from asago_scenario_generator.pipeline.generate import actor
    from asago_scenario_generator.pipeline.generate import behavior_semantics as behavior

    actor_prompt = actor._actor_draft_prompt
    behavior_model = behavior.build_behavior_draft_response_model
    with pytest.raises(RuntimeError):
        with generation_compatibility(provider="ollama", demo_preset=False):
            assert behavior.build_behavior_draft_response_model is behavior_model
            prompt = actor._actor_draft_prompt({"c0": ("external_attacker", "intermediate")}, {})
            assert "choose an advanced" not in prompt
            raise RuntimeError("model unavailable")
    assert actor._actor_draft_prompt is actor_prompt
    assert behavior.build_behavior_draft_response_model is behavior_model


def test_pacer_spaces_request_starts_including_retries():
    from asago_demo.generation import RequestPacer

    now = [0.0]
    waits = []

    def sleep(delay):
        waits.append(delay)
        now[0] += delay

    pacer = RequestPacer(4.2, clock=lambda: now[0], sleep=sleep)
    pacer.wait()
    pacer.wait()
    now[0] += 2
    pacer.wait()
    assert waits == pytest.approx([4.2, 2.2])


def test_demo_tree_prompt_preserves_supplied_order():
    from types import SimpleNamespace

    from asago_scenario_generator.pipeline.generate import tree

    original = tree._semantic_user_prompt
    inventory = [{"handle": "l2"}, {"handle": "l0"}]
    with generation_compatibility(provider="google", demo_preset=True):
        prompt = tree._semantic_user_prompt(
            "demo",
            SimpleNamespace(attack_pattern_name="test"),
            SimpleNamespace(title="title", summary="summary"),
            inventory,
            None,
        )
        assert '["l2", "l0"]' in prompt
        assert "one group" in prompt
    assert tree._semantic_user_prompt is original


def test_recording_filter_prompt_states_the_existing_length_bound(monkeypatch):
    from types import SimpleNamespace

    from asago_scenario_generator.llm.client import LLMClient

    seen = {}

    def complete(self, system_prompt, user_prompt, response_format=None):
        seen.update(prompt=user_prompt, model=response_format)
        return "unchanged result"

    monkeypatch.setattr(LLMClient, "complete", complete)
    response_model = type("FilterMapDraftV3For1Candidates", (), {})
    with generation_compatibility(provider="google", demo_preset=True):
        result = LLMClient.complete(
            SimpleNamespace(model="gemini-3.1-flash-lite"),
            "system",
            "candidate inventory",
            response_format=response_model,
        )
    assert result == "unchanged result"
    assert seen["model"] is response_model
    assert "220 characters" in seen["prompt"]


@pytest.mark.parametrize("provider", ["ollama", "litellm"])
def test_non_google_models_keep_native_schema(provider):
    from asago_scenario_generator.pipeline.generate import behavior_semantics as behavior

    response_model = behavior.build_behavior_draft_response_model
    with generation_compatibility(provider=provider, demo_preset=True):
        assert behavior.build_behavior_draft_response_model is response_model
        assert (
            response_model(["a0", "p0"]).model_json_schema()["properties"]["scenarios"]["maxItems"]
            == 8
        )


def test_ollama_serializes_concurrent_requests_without_google_schema_or_pacing(monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from asago_scenario_generator.llm.client import LLMClient

    from asago_demo.generation import RequestPacer

    active = 0
    peak = 0
    lock = threading.Lock()

    def complete(self, system_prompt, user_prompt, response_format=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
        time.sleep(0.02)
        with lock:
            active -= 1
        return user_prompt

    def unexpected_pacing(_self):
        raise AssertionError("Google pacing must not apply to Ollama")

    monkeypatch.setattr(LLMClient, "complete", complete)
    monkeypatch.setattr(RequestPacer, "wait", unexpected_pacing)
    with generation_compatibility(provider="ollama", demo_preset=True):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(
                pool.map(
                    lambda i: LLMClient.complete(
                        SimpleNamespace(model="qwen2.5:14b"), "system", str(i)
                    ),
                    range(3),
                )
            )
    assert peak == 1
    assert results == ["0", "1", "2"]
    assert LLMClient.complete is complete
