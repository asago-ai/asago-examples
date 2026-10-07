"""Real stage entry points, shared by the dashboard and prepared notebooks."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asago_demo.artifact_context import adapt_context  # noqa: E402
from asago_demo.evaluation import evaluation  # noqa: E402
from asago_demo.runtime import (  # noqa: E402
    SCENARIO_PROFILES,
    STAGES,
    atomic_json,
    model_connection,
    redact_value,
    safe_child,
    scenario_options,
)

EXAMPLES = ROOT.parent
INPUTS = EXAMPLES / "asago-scenario-generator/inputs"


def configure_environment(config):
    connection = model_connection(config, "scenario")
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[variable] = "1"
    os.environ.update(
        {
            "ASAGO_SCENARIO_GENERATOR_MODEL_BASE_URL": connection["base_url"],
            "ASAGO_SCENARIO_GENERATOR_MODEL_NAME": connection["model"],
            "ASAGO_SCENARIO_GENERATOR_API_KEY": connection["api_key"],
            "ASAGO_SCENARIO_GENERATOR_TEMPERATURE": "0.4",
            "ASAGO_SCENARIO_GENERATOR_TIMEOUT": str(config.get("timeout", 300)),
        }
    )


def policy(run: Path, config: dict) -> dict:
    """Load committed evidence and rebuild the actual PR #79 report, with no LLM call."""
    from asago_demo.reporting import build_policy_report

    folder = run / "policy"
    folder.mkdir(exist_ok=True)
    source = INPUTS / "risk-extractions/risk-extraction-fs-isac.json"
    extraction = folder / "risk-extraction.json"
    print("[Stage Policy] Loading saved FS-ISAC extraction. No policy model calls.", flush=True)
    shutil.copyfile(source, extraction)
    shutil.copyfile(
        EXAMPLES / "asago-policy-mapper/policy_examples/fs-isac.pdf", folder / "policy.pdf"
    )
    data = json.loads(extraction.read_text())
    report = build_policy_report(data, folder / "report.html")
    risks = data.get("risks", [])
    print(f"[Stage Policy report] Ready: {len(risks)} matched taxonomy entries.", flush=True)
    return {
        "status": "completed",
        "source": "saved",
        "policy": "FS-ISAC generative AI policy",
        "report": str(report.relative_to(run)),
        "extraction": str(extraction.relative_to(run)),
        "count": len(risks),
        "taxonomies": sorted({r.get("taxonomy", "") for r in risks}),
        "risks": [
            {
                k: r.get(k)
                for k in ("risk_id", "risk_name", "taxonomy", "grounding_confidence", "evidence")
            }
            for r in risks
        ],
    }


def summarize_scenarios(run: Path, run_dir: Path) -> dict:
    import yaml
    from asago_artifact_generator.extract import load_scenario
    from asago_artifact_generator.garak.classify import lookup_surface, surface_skip_reason

    inventory_path = run_dir / "finalization-inventory.json"
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
    decisions = inventory.get("admission_decisions", [])
    rows = []
    for path in sorted(run_dir.glob("scenarios/**/*.yaml")):
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict) or not data.get("scenario_id"):
            continue
        ctx = adapt_context(load_scenario(path))
        narrative = data.get("narrative") or {}
        faceting = data.get("faceting") or {}
        risk = faceting.get("risk_card") or {}
        feature = path.with_suffix(".feature")
        rows.append(
            {
                "id": data["scenario_id"],
                "title": narrative.get("title", data["scenario_id"]),
                "summary": narrative.get("summary", ""),
                "entry_point": ctx.entry_point,
                "surface": lookup_surface(ctx),
                "skip_reason": surface_skip_reason(ctx),
                "risk_id": risk.get("risk_id", ""),
                "file": str(path.relative_to(run)),
                "data": data,
                "gherkin": feature.read_text() if feature.exists() else ctx.behavior_spec,
            }
        )
    admitted = sum(d.get("admitted") is True for d in decisions)
    quarantined = len(decisions) - admitted
    report = run_dir / "report.html"
    errors = []
    for path in sorted((run_dir / "quarantine").glob("*.json")):
        errors.append(
            {"file": str(path.relative_to(run)), "details": json.loads(path.read_text())}
        )
    return {
        "status": "completed" if rows else "failed",
        "source": "live",
        "error": ""
        if rows
        else "No scenarios were admitted. Inspect rejected scenarios and coverage gaps.",
        "run_dir": str(run_dir.relative_to(run)),
        "scenarios": rows,
        "admitted": admitted if decisions else len(rows),
        "quarantined": quarantined,
        "report": str(report.relative_to(run)) if report.exists() else None,
        "inventory": inventory,
        "quarantine": errors,
    }


def prepare_demo_scope(run: Path, scope: str) -> Path | None:
    """Use the pipeline's public threat input to bound seeds before LLM filtering."""
    if scope == "full":
        return None
    import yaml
    from asago_scenario_generator.data.loaders import load_attack_patterns
    from asago_scenario_generator.data.paths import DATA_ROOT

    selected = {"T5"}
    expected = {"AP-T5-01", "AP-T5-02", "AP-T5-04"}
    if scope == "recording":
        selected.add("T10")
        expected.add("AP-T10-01")
    if scope == "indirect":
        selected = {"T6"}
        expected = {f"AP-T6-{i:02}" for i in range(1, 8)}
    actual = {p["id"] for p in load_attack_patterns().values() if p["threat_id"] in selected}
    if actual != expected:
        raise ValueError("The installed attack catalog changed. Update the demo preset.")
    source = DATA_ROOT / "taxonomies/owasp-agentic-threats/owasp-agentic-threats-v1.1.yaml"
    data = yaml.safe_load(source.read_text())
    data["threats"] = {key: value for key, value in data["threats"].items() if key in selected}
    path = run / f"{scope}-threats.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    print(
        f"[Stage Demo scope] Checking only {len(expected)} attack patterns: "
        + ", ".join(sorted(expected))
        + ". Qualification and validation stay enabled.",
        flush=True,
    )
    return path


def scenarios(run: Path, config: dict) -> dict:
    from asago_scenario_generator.pipeline.runner import run_pipeline

    from asago_demo.generation import generation_compatibility

    extraction = run / "policy/risk-extraction.json"
    if not extraction.is_file():
        raise ValueError("Load the saved policy extraction first")
    options = scenario_options(config)
    connection = model_connection(config, "scenario")
    threats_path = prepare_demo_scope(run, options["scenario_scope"])
    print("Generating Klarna scenarios from this run's saved FS-ISAC extraction.", flush=True)
    print(
        f"Scenario configuration: {json.dumps(options)}; one technique per scenario.",
        flush=True,
    )
    with generation_compatibility(
        provider=connection["provider"],
        demo_preset=options["scenario_scope"] in {"recording", "indirect"},
    ):
        result = run_pipeline(
            use_case=(INPUTS / "use-cases/use-case-klarna-fs-isac-v36.txt").read_text(),
            risk_extraction_path=extraction,
            sssom_path=INPUTS / "mappings/risk_to_category.sssom.tsv",
            output_dir=run / "scenario-generation",
            profile_path=INPUTS / "profiles" / SCENARIO_PROFILES[options["scenario_profile"]],
            qualification_facts_path=INPUTS / "profiles/klarna-qualification-facts.yaml",
            threats_path=threats_path,
            base_url=connection["base_url"],
            api_key=connection["api_key"],
            model=connection["model"],
            max_techniques=1,
            max_scenarios_per_pattern=options["max_scenarios_per_pattern"],
            generation_mode=options["generation_mode"],
            eval=True,
        )
    data = summarize_scenarios(run, Path(result.run_dir))
    data["generation_options"] = options
    if threats_path:
        data["scope_file"] = threats_path.name
    print(f"Scenarios: {data['admitted']} admitted, {data['quarantined']} rejected.", flush=True)
    return data


def artifact(run: Path, config: dict) -> dict:
    from asago_artifact_generator.extract import load_scenario
    from asago_artifact_generator.garak.classify import surface_skip_reason
    from asago_artifact_generator.garak.gen import generate_artifact
    from asago_artifact_generator.garak.spec_io import validation_path
    from asago_artifact_generator.llm import configure_llm

    data = json.loads((run / "scenarios.json").read_text())
    choices = {s["file"]: s for s in data.get("scenarios", [])}
    selected = run / "selection.json"
    if selected.exists():
        filename = json.loads(selected.read_text())["scenario"]
    else:
        filename = next((s["file"] for s in choices.values() if not s["skip_reason"]), "")
    if filename not in choices:
        raise ValueError("No admitted scenario supports Garak. Inspect the scenario results.")
    ctx = adapt_context(load_scenario(safe_child(run, filename)))
    reason = surface_skip_reason(ctx)
    if reason:
        raise ValueError(f"This scenario cannot run in Garak: {reason}")
    connection = model_connection(config, "artifact")
    model = connection["model"]
    configure_llm(
        provider="openai",
        base_url=connection["base_url"],
        api_key=connection["api_key"],
        model=model,
    )
    print(
        f"[Stage Artifact] Generating and validating {ctx.scenario_id} with {model}.", flush=True
    )
    result = generate_artifact(ctx, output_dir=run / "artifacts", force=False, max_attempts=3)
    validation_file = validation_path(ctx.scenario_id, run / "artifacts")
    validation = json.loads(validation_file.read_text()) if validation_file.exists() else {}
    artifact_file = Path(result.artifact_path) if result.artifact_path else None
    artifact_data = (
        json.loads(artifact_file.read_text()) if artifact_file and artifact_file.exists() else {}
    )
    ok = result.ok and bool(artifact_data) and result.gate != "skip"
    print(f"Coverage: {result.gate}; validation: {'passed' if ok else 'failed'}.", flush=True)
    return {
        "status": "completed" if ok else "failed",
        "source": "live",
        "error": "" if ok else "; ".join(result.errors or ["Artifact validation did not pass"]),
        "scenario_id": ctx.scenario_id,
        "scenario_file": filename,
        "coverage": result.gate,
        "coverage_reason": result.gate_reason,
        "validation": validation,
        "artifact": artifact_data,
        "file": str(artifact_file.relative_to(run)) if artifact_file else None,
        "validation_file": str(validation_file.relative_to(run))
        if validation_file.exists()
        else None,
    }


def run_stage(stage: str, run: Path, config: dict) -> dict:
    if stage not in STAGES:
        raise ValueError("Unknown stage")
    configure_environment(config)
    if stage != "scenarios":
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        result = {
            "policy": policy,
            "scenarios": scenarios,
            "artifact": artifact,
            "evaluation": evaluation,
        }[stage](run, config)
    except Exception as exc:
        error = redact_value(str(exc), config)
        print(f"{stage} stopped: {error}", flush=True)
        result = {"status": "failed", "error": error}
    result = redact_value(result, config)
    atomic_json(run / f"{stage}.json", result)
    return result


if __name__ == "__main__":
    result = run_stage(sys.argv[1], Path(sys.argv[2]), json.loads(os.environ["ASAGO_DEMO_CONFIG"]))
    raise SystemExit(0 if result["status"] == "completed" else 1)
