import json
import sys
import time
from pathlib import Path

import pytest

from asago_demo.runtime import Coordinator, Settings, redacted_file, safe_child


def test_google_uses_its_own_key_and_fixed_endpoint(tmp_path):
    from asago_demo.runtime import model_connection, redact_value

    settings = Settings(
        tmp_path, defaults={"api_key": "proxy-secret", "base_url": "https://proxy.example/v1"}
    )
    settings.update(
        {
            "google_api_key": "google-secret",
            "scenario_provider": "google",
            "model": "gemini-flash-test",
        }
    )
    config = settings.private()
    expected = {
        "provider": "google",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": "google-secret",
        "model": "gemini-flash-test",
    }
    assert model_connection(config, "scenario") == expected
    assert model_connection(config, "artifact") == expected
    assert model_connection(config, "judge") == expected
    settings.update({"model": "models/gemini-flash-test"})
    assert model_connection(settings.private(), "scenario")["model"] == "gemini-flash-test"
    assert model_connection(config, "target")["api_key"] == "ollama"
    settings.update({"google_api_key": "", "api_key": ""})
    assert settings.private()["google_api_key"] == "google-secret"
    assert settings.public()["google_api_key_configured"]
    assert "google-secret" not in json.dumps(settings.public())
    assert "proxy-secret" not in json.dumps(settings.public())
    assert redact_value("google-secret proxy-secret", config) == "[redacted] [redacted]"
    settings.update({"scenario_provider": "litellm", "model": "gemma"})
    assert model_connection(settings.private(), "scenario")["api_key"] == "proxy-secret"


def test_google_requires_key_before_saving_selected_role(tmp_path):
    settings = Settings(tmp_path, defaults={})
    with pytest.raises(ValueError, match="Google.*key"):
        settings.update({"scenario_provider": "google", "model": "gemini-flash-test"})
    assert not settings.path.exists()


def test_models_can_use_independent_services_without_leaking_litellm_key(tmp_path):
    from asago_demo.runtime import model_connection

    settings = Settings(
        tmp_path,
        defaults={
            "base_url": "https://proxy.example/v1",
            "api_key": "proxy-secret",
            "model": "gemma",
            "target_model": "qwen",
            "target_base_url": "http://localhost:11434/v1",
        },
    )
    settings.update(
        {
            "scenario_provider": "ollama",
            "model": "qwen:14b",
            "ollama_base_url": "http://localhost:11434",
            "artifact_provider": "litellm",
            "artifact_model": "gemma",
            "target_provider": "litellm",
            "target_model": "target-remote",
            "judge_provider": "ollama",
            "judge_model": "judge-local",
        }
    )
    config = Settings(tmp_path, defaults={}).private()
    assert model_connection(config, "scenario") == {
        "provider": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "qwen:14b",
    }
    assert model_connection(config, "artifact")["api_key"] == "proxy-secret"
    assert model_connection(config, "target")["model"] == "target-remote"
    assert model_connection(config, "target")["base_url"] == "https://proxy.example/v1"
    assert model_connection(config, "judge")["api_key"] == "ollama"
    assert model_connection(config, "judge")["model"] == "judge-local"
    assert "proxy-secret" not in json.dumps(settings.public())


def test_legacy_connections_and_inherited_models_are_preserved():
    from asago_demo.runtime import model_connection

    config = {
        "base_url": "https://proxy.example/v1",
        "api_key": "key",
        "model": "gemma",
        "artifact_model": "artifact-gemma",
        "target_base_url": "http://custom:11434/v1",
        "target_model": "qwen",
    }
    assert model_connection(config, "scenario")["model"] == "gemma"
    assert model_connection(config, "artifact")["model"] == "artifact-gemma"
    assert model_connection(config, "judge")["model"] == "artifact-gemma"
    assert model_connection(config, "target")["base_url"] == "http://custom:11434/v1"
    config.update(scenario_provider="ollama", artifact_model="")
    assert model_connection(config, "judge")["provider"] == "ollama"
    assert model_connection(config, "judge")["api_key"] == "ollama"


@pytest.mark.parametrize(
    "changes",
    [
        {"scenario_provider": "other"},
        {"target_provider": "same"},
        {"artifact_provider": "ollama", "artifact_model": ""},
        {"judge_provider": "litellm", "judge_model": ""},
        {"ollama_base_url": "file:///private"},
    ],
)
def test_invalid_model_configuration_is_not_saved(tmp_path, changes):
    settings = Settings(tmp_path, defaults={})
    with pytest.raises(ValueError):
        settings.update(changes)
    assert not settings.path.exists()


def test_model_discovery_preview_does_not_save_drafts(tmp_path):
    settings = Settings(tmp_path, defaults={"api_key": "saved-key"})
    draft = settings.preview({"base_url": "https://draft.example/v1", "api_key": ""})
    assert draft["api_key"] == "saved-key"
    assert draft["base_url"] == "https://draft.example/v1"
    assert not settings.path.exists()


def test_saving_model_choices_requires_urls_only_for_selected_services(tmp_path):
    settings = Settings(tmp_path, defaults={})
    with pytest.raises(ValueError, match="URL"):
        settings.update({"scenario_provider": "litellm", "model": "gemma", "base_url": ""})
    assert not settings.path.exists()
    settings.update({"scenario_provider": "ollama", "model": "qwen", "base_url": ""})
    assert settings.private()["scenario_provider"] == "ollama"


def wait_for_finish(coordinator):
    deadline = time.monotonic() + 5
    while coordinator.busy and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not coordinator.busy
    return coordinator.current()


def test_secrets_are_preserved_but_never_returned(tmp_path):
    settings = Settings(
        tmp_path,
        defaults={
            "api_key": "private-key",
            "model": "gemma",
            "base_url": "https://proxy.example/v1",
        },
    )
    settings.update({"api_key": "", "model": "new-model"})
    assert settings.private()["api_key"] == "private-key"
    public = settings.public()
    assert "private-key" not in json.dumps(public)
    assert "api_key" not in public
    assert public["api_key_configured"]
    assert settings.path.stat().st_mode & 0o077 == 0


def test_settings_reject_unknown_fields_and_bad_urls(tmp_path):
    settings = Settings(tmp_path, defaults={})
    with pytest.raises(ValueError):
        settings.update({"command": "anything"})
    with pytest.raises(ValueError):
        settings.update({"base_url": "file:///tmp/private"})


def test_scenario_choices_persist_without_replacing_connection_settings(tmp_path):
    settings = Settings(tmp_path, defaults={"api_key": "private-key", "model": "gemma"})
    settings.update(
        {
            "scenario_profile": "full",
            "generation_mode": "exhaustive",
            "max_scenarios_per_pattern": 3,
        }
    )
    restored = Settings(tmp_path, defaults={}).public()
    assert restored["scenario_profile"] == "full"
    assert restored["generation_mode"] == "exhaustive"
    assert restored["max_scenarios_per_pattern"] == 3
    assert restored["model"] == "gemma"
    assert settings.private()["api_key"] == "private-key"


@pytest.mark.parametrize(
    "changes",
    [
        {"scenario_profile": "../custom.yaml"},
        {"scenario_scope": "unbounded"},
        {"generation_mode": "unknown"},
        {"max_scenarios_per_pattern": 0},
        {"max_scenarios_per_pattern": 11},
        {"max_scenarios_per_pattern": True},
        {"max_scenarios_per_pattern": "3"},
    ],
)
def test_invalid_scenario_choices_do_not_replace_saved_settings(tmp_path, changes):
    settings = Settings(tmp_path, defaults={})
    settings.update({"scenario_profile": "full"})
    before = settings.path.read_text()
    with pytest.raises(ValueError):
        settings.update(changes)
    assert settings.path.read_text() == before


def test_scenario_run_records_the_options_sent_to_its_worker(tmp_path, monkeypatch):
    code = """
import json, os, sys
from pathlib import Path
stage, root = sys.argv[1], Path(sys.argv[2])
config = json.loads(os.environ['ASAGO_DEMO_CONFIG'])
result = {'status': 'completed'}
if stage == 'scenarios':
    result['options_received'] = {key: config[key] for key in
        ('scenario_scope', 'scenario_profile', 'generation_mode', 'max_scenarios_per_pattern')}
(root / (stage + '.json')).write_text(json.dumps(result))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.settings.update(
        {
            "scenario_profile": "full",
            "generation_mode": "exhaustive",
            "max_scenarios_per_pattern": 2,
        }
    )
    c.start("all")
    state = wait_for_finish(c)
    expected = {
        "scenario_scope": "full",
        "scenario_profile": "full",
        "generation_mode": "exhaustive",
        "max_scenarios_per_pattern": 2,
    }
    assert state["results"]["scenarios"]["options_received"] == expected
    assert state["stages"]["scenarios"]["generation_options"] == expected
    c.settings.update({"scenario_profile": "direct", "generation_mode": "coverage"})
    assert c.current()["stages"]["scenarios"]["generation_options"] == expected


def test_download_paths_cannot_escape_even_through_symlinks(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    (root / "file.json").write_text("{}")
    (tmp_path / "private").write_text("secret")
    (root / "link").symlink_to(tmp_path / "private")
    assert safe_child(root, "file.json").is_file()
    for name in ["../private", "link", str(tmp_path / "private")]:
        with pytest.raises(ValueError):
            safe_child(root, name)


def make_coordinator(tmp_path, monkeypatch, script):
    coordinator = Coordinator(tmp_path, Settings(tmp_path, defaults={"api_key": "hide-me"}))
    monkeypatch.setattr(
        coordinator,
        "command",
        lambda stage, run: [sys.executable, "-u", "-c", script, stage, str(run)],
    )
    return coordinator


def test_run_all_connects_stages_and_redacts_logs(tmp_path, monkeypatch):
    code = """
import json,sys
from pathlib import Path
stage,root = sys.argv[1],Path(sys.argv[2])
order=['policy','scenarios','artifact','evaluation']
index=order.index(stage)
if index: assert (root/(order[index-1]+'.json')).exists()
print('hide-me')
(root/(stage+'.json')).write_text(json.dumps({'status':'completed','stage':stage}))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.start("all")
    state = wait_for_finish(c)
    assert state["status"] == "completed"
    assert all(s["status"] == "completed" for s in state["stages"].values())
    assert "hide-me" not in json.dumps(state)
    assert "hide-me" not in (Path(state["_path"]) / "console.log").read_text()
    assert state["activity"]["status"] == "completed"
    assert state["activity"]["ended"] >= state["activity"]["started"]
    assert state["activity"]["stages"] == ["policy", "scenarios", "artifact", "evaluation"]
    for stage in state["activity"]["stages"]:
        assert any(f"[{stage}] Stage completed" in line for line in state["logs"])


def test_rerun_resets_activity_and_keeps_previous_logs(tmp_path, monkeypatch):
    code = """
import json,sys
from pathlib import Path
stage,root = sys.argv[1],Path(sys.argv[2])
print('OUTPUT-' + stage)
(root/(stage+'.json')).write_text(json.dumps({'status':'completed'}))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.start("all")
    previous = wait_for_finish(c)
    folder = Path(previous["_path"])
    previous_log = (folder / previous["activity"]["log_file"]).read_text()
    c.start("scenarios")
    current = wait_for_finish(c)
    assert "OUTPUT-policy" not in "\n".join(current["logs"])
    assert "OUTPUT-scenarios" in "\n".join(current["logs"])
    assert "OUTPUT-evaluation" not in (folder / "console.log").read_text()
    assert (folder / previous["activity"]["log_file"]).read_text() == previous_log
    assert current["activity_history"][-1]["id"] == previous["activity"]["id"]
    assert current["activity"]["id"] != previous["activity"]["id"]
    assert current["activity"]["stages"] == ["scenarios"]


def test_activity_exposes_pipeline_step_and_timeouts_without_secrets(tmp_path, monkeypatch):
    code = """
import json,sys
from pathlib import Path
print('[Stage 3.5] Expanding and filtering candidates...')
print('WARNING Filter request timed out hide-me — retrying')
(Path(sys.argv[2])/(sys.argv[1]+'.json')).write_text(
    json.dumps({'status':'failed','error':'Endpoint timed out hide-me'}))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.start("policy")
    state = wait_for_finish(c)
    activity = state["activity"]
    assert "filtering candidates" in activity["phase"]
    assert "retrying" in activity["last_warning"]
    assert activity["warning_count"] == 1
    assert activity["last_output_at"] >= activity["started"]
    assert activity["status"] == "failed"
    assert "timed out" in activity["error"]
    assert "hide-me" not in json.dumps(state)
    assert any("Stage failed" in line for line in state["logs"])


def test_restart_finishes_interrupted_activity(tmp_path, monkeypatch):
    c = make_coordinator(tmp_path, monkeypatch, "import time; time.sleep(30)")
    c.start("policy")
    c.cancel()
    state = wait_for_finish(c)
    assert state["activity"]["status"] == "cancelled"
    assert state["activity"]["ended"] >= state["activity"]["started"]
    state["status"] = state["activity"]["status"] = "running"
    (Path(state["_path"]) / "state.json").write_text(json.dumps(state))
    restored = Coordinator(tmp_path, c.settings).current()
    assert restored["activity"]["status"] == "interrupted"
    assert "Server stopped" in restored["activity"]["error"]


def test_legacy_log_is_archived_before_first_rerun(tmp_path, monkeypatch):
    code = """
import json,sys
from pathlib import Path
(Path(sys.argv[2])/(sys.argv[1]+'.json')).write_text(json.dumps({'status':'completed'}))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.start("all")
    state = wait_for_finish(c)
    state.pop("activity")
    state["error"] = "old failure"
    folder = Path(state["_path"])
    (folder / "state.json").write_text(json.dumps(state))
    (folder / "console.log").write_text("Legacy activity\n")
    c.start("scenarios")
    current = wait_for_finish(c)
    assert "error" not in current
    assert (
        folder / current["activity_history"][-1]["log_file"]
    ).read_text() == "Legacy activity\n"
    assert "Legacy activity" not in (folder / "console.log").read_text()


def test_failure_stops_dependent_stages(tmp_path, monkeypatch):
    c = make_coordinator(
        tmp_path, monkeypatch, "import sys; print('failure details'); sys.exit(2)"
    )
    c.start("all")
    state = wait_for_finish(c)
    assert state["status"] == "failed"
    assert state["stages"]["policy"]["status"] == "failed"
    assert state["stages"]["scenarios"]["status"] == "pending"


def test_non_completed_result_is_not_success(tmp_path, monkeypatch):
    code = """
import sys,json
from pathlib import Path
data = {'status':'failed','error':'No admitted scenarios'}
(Path(sys.argv[2])/(sys.argv[1]+'.json')).write_text(json.dumps(data))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.start("policy")
    state = wait_for_finish(c)
    assert state["status"] == "failed"
    assert "No admitted" in state["stages"]["policy"]["error"]


def test_concurrent_runs_rejected_and_cancel_stops_worker(tmp_path, monkeypatch):
    c = make_coordinator(tmp_path, monkeypatch, "import time; time.sleep(30)")
    c.start("policy")
    with pytest.raises(ValueError, match="running"):
        c.start("policy")
    c.cancel()
    state = wait_for_finish(c)
    assert state["status"] == "cancelled"


def test_missing_upstream_results_rejected(tmp_path):
    c = Coordinator(tmp_path, Settings(tmp_path, defaults={}))
    with pytest.raises(ValueError, match="Policy"):
        c.start("scenarios")


def test_missing_result_file_fails_even_if_worker_exits_zero(tmp_path, monkeypatch):
    c = make_coordinator(tmp_path, monkeypatch, "print('no result produced')")
    c.start("policy")
    assert wait_for_finish(c)["status"] == "failed"


def test_returned_failure_payload_is_redacted(tmp_path, monkeypatch):
    code = """
import sys,json
from pathlib import Path
data={'status':'failed','error':'hide-me','nested':{'validation':['hide-me']}}
(Path(sys.argv[2])/(sys.argv[1]+'.json')).write_text(json.dumps(data))
"""
    c = make_coordinator(tmp_path, monkeypatch, code)
    c.start("policy")
    state = wait_for_finish(c)
    assert "hide-me" not in json.dumps(state)
    assert "hide-me" not in (Path(state["_path"]) / "policy.json").read_text()


def test_stale_cancellation_does_not_stop_another_job(tmp_path, monkeypatch):
    c = make_coordinator(tmp_path, monkeypatch, "import time; time.sleep(30)")
    run_id = c.start("policy")
    assert not c.cancel("old-run", "policy")
    assert not c.cancel(run_id, "scenarios")
    assert not c.stop.is_set()
    c.cancel(run_id, "policy")
    assert wait_for_finish(c)["status"] == "cancelled"


@pytest.mark.parametrize("suffix", [".json", ".jsonl"])
def test_redaction_preserves_json_with_quoted_bearer_text(tmp_path, suffix):
    path = tmp_path / ("result" + suffix)
    path.write_text(json.dumps({"text": 'Use "Authorization: Bearer example-token".'}))
    clean = redacted_file(path, {})
    assert json.loads(clean)["text"] == 'Use "Authorization: Bearer [redacted]".'


def test_recording_preset_is_repeatable_and_preserves_credentials(tmp_path):
    from asago_demo.runtime import DEMO_PRESET, scenario_options

    settings = Settings(tmp_path, defaults={"google_api_key": "saved-google-key"})
    settings.update(DEMO_PRESET)
    restored = Settings(tmp_path, defaults={})
    assert restored.private()["google_api_key"] == "saved-google-key"
    assert all(restored.public()[key] == value for key, value in DEMO_PRESET.items())
    options = scenario_options(
        {
            **DEMO_PRESET,
            "scenario_profile": "full",
            "generation_mode": "coverage",
            "max_scenarios_per_pattern": 9,
        }
    )
    assert options == {
        "scenario_scope": "recording",
        "scenario_profile": "direct",
        "generation_mode": "exhaustive",
        "max_scenarios_per_pattern": 1,
    }


@pytest.mark.parametrize("provider", ["google", "ollama", "litellm"])
def test_presets_preserve_selected_models_and_connections(tmp_path, provider):
    from asago_demo.runtime import SCENARIO_PRESETS

    settings = Settings(
        tmp_path,
        defaults={
            "scenario_provider": provider,
            "model": "chosen-model",
            "judge_provider": "ollama",
            "judge_model": "chosen-judge",
            "google_api_key": "google-secret",
            "api_key": "proxy-secret",
            "timeout": 300,
        },
    )
    before = settings.private()
    for preset in SCENARIO_PRESETS.values():
        settings.update(preset)
        after = settings.private()
        for key in (
            "scenario_provider",
            "model",
            "judge_provider",
            "judge_model",
            "google_api_key",
            "api_key",
            "timeout",
        ):
            assert after[key] == before[key]
