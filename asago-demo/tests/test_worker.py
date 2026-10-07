from types import SimpleNamespace

import pytest

from asago_demo import worker


@pytest.mark.parametrize(("scope", "count"), [("quick3", 3), ("recording", 4)])
def test_quick_scope_restricts_real_seed_expansion_before_model_calls(tmp_path, scope, count):
    import yaml
    from asago_scenario_generator.data.loaders import load_risk_extraction
    from asago_scenario_generator.data.paths import DATA_ROOT
    from asago_scenario_generator.models import CapabilityProfile
    from asago_scenario_generator.pipeline.seeds import expand_seeds
    from asago_scenario_generator.pipeline.threats import determine_threat_surface

    path = worker.prepare_demo_scope(tmp_path, scope)
    profile = CapabilityProfile.model_validate(
        yaml.safe_load((worker.INPUTS / "profiles/klarna-direct-canary-profile.yaml").read_text())
    )
    surface = determine_threat_surface(
        profile,
        load_risk_extraction(worker.INPUTS / "risk-extractions/risk-extraction-fs-isac.json"),
        worker.INPUTS / "mappings/risk_to_category.sssom.tsv",
        DATA_ROOT / "taxonomies/mappings/cross-taxonomy-mappings.yaml",
        path,
    )
    seeds = expand_seeds(surface, path)
    assert len(seeds) == count
    assert {seed.seed_id for seed in seeds} == (
        {"AP-T5-01", "AP-T5-02", "AP-T5-04"} | ({"AP-T10-01"} if scope == "recording" else set())
    )


def test_quick_scope_uses_one_scenario_per_pattern(tmp_path, monkeypatch):
    from asago_scenario_generator.pipeline import runner

    (tmp_path / "policy").mkdir()
    (tmp_path / "policy/risk-extraction.json").write_text("{}")
    calls = []

    def pipeline(**kwargs):
        calls.append(kwargs)
        output = tmp_path / "scenario-generation/test"
        output.mkdir(parents=True)
        return SimpleNamespace(run_dir=output)

    monkeypatch.setattr(runner, "run_pipeline", pipeline)
    worker.scenarios(
        tmp_path,
        {"model": "test", "base_url": "https://example.test/v1", "scenario_scope": "quick3"},
    )
    assert calls[0]["threats_path"].is_file()
    assert calls[0]["generation_mode"] == "exhaustive"
    assert calls[0]["max_scenarios_per_pattern"] == 1
    assert calls[0]["eval"] is True


@pytest.mark.parametrize(
    ("options", "profile", "mode", "cap"),
    [
        ({}, "klarna-direct-canary-profile.yaml", "coverage", 1),
        (
            {
                "scenario_profile": "full",
                "generation_mode": "exhaustive",
                "max_scenarios_per_pattern": 3,
            },
            "klarna-capability-profile.yaml",
            "exhaustive",
            3,
        ),
    ],
)
def test_worker_applies_scenario_choices_at_the_pipeline_boundary(
    tmp_path, monkeypatch, options, profile, mode, cap
):
    from asago_scenario_generator.pipeline import runner

    (tmp_path / "policy").mkdir()
    (tmp_path / "policy/risk-extraction.json").write_text("{}")
    calls = []

    def pipeline(**kwargs):
        calls.append(kwargs)
        output = tmp_path / "scenario-generation/test"
        output.mkdir(parents=True)
        return SimpleNamespace(run_dir=output)

    # Only model generation is replaced; real option resolution and summarization run.
    monkeypatch.setattr(runner, "run_pipeline", pipeline)
    config = {"base_url": "https://example.test/v1", "model": "test", **options}
    if options:
        config.update(
            scenario_provider="ollama",
            ollama_base_url="http://localhost:11434",
            api_key="never-send-to-ollama",
        )
    worker.configure_environment(config)
    worker.scenarios(tmp_path, config)
    assert len(calls) == 1
    assert calls[0]["profile_path"].name == profile
    assert calls[0]["profile_path"].is_file()
    assert calls[0]["generation_mode"] == mode
    assert calls[0]["max_scenarios_per_pattern"] == cap
    assert calls[0]["base_url"] == (
        "http://localhost:11434/v1" if options else "https://example.test/v1"
    )
    assert calls[0]["api_key"] == ("ollama" if options else "none")
    import os

    assert os.environ["ASAGO_SCENARIO_GENERATOR_MODEL_BASE_URL"] == calls[0]["base_url"]


def test_indirect_preset_bounds_scope_and_preserves_validation(tmp_path, monkeypatch):
    import yaml
    from asago_scenario_generator.pipeline import runner

    from asago_demo.runtime import SCENARIO_PRESETS, scenario_options

    (tmp_path / "policy").mkdir()
    (tmp_path / "policy/risk-extraction.json").write_text("{}")
    calls = []

    def pipeline(**kwargs):
        calls.append(kwargs)
        output = tmp_path / "scenario-generation/test"
        output.mkdir(parents=True)
        return SimpleNamespace(run_dir=output)

    monkeypatch.setattr(runner, "run_pipeline", pipeline)
    config = {**SCENARIO_PRESETS["indirect"], "google_api_key": "offline"}
    worker.scenarios(tmp_path, config)
    call = calls[0]
    profile = yaml.safe_load(call["profile_path"].read_text())
    assert {e["controllability"] for e in profile["entry_points"]} == {"indirect"}
    assert call["max_scenarios_per_pattern"] == 3
    assert call["generation_mode"] == "exhaustive"
    assert call["eval"] is True
    assert set(yaml.safe_load(call["threats_path"].read_text())["threats"]) == {"T6"}
    assert scenario_options(config)["scenario_profile"] == "indirect"
