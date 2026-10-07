"""Read-only preview of the installed pipeline's full-search expansion; no LLM calls."""

from functools import lru_cache


@lru_cache(maxsize=1)
def full_search_plan() -> dict:
    import yaml
    from asago_scenario_generator.data.loaders import load_risk_extraction
    from asago_scenario_generator.data.paths import DATA_ROOT
    from asago_scenario_generator.models import CapabilityProfile
    from asago_scenario_generator.pipeline.candidates import (
        apply_rule_based_filter,
        expand_candidates,
    )
    from asago_scenario_generator.pipeline.seeds import expand_seeds
    from asago_scenario_generator.pipeline.threats import determine_threat_surface

    from asago_demo.runtime import SCENARIO_PROFILES
    from asago_demo.worker import INPUTS

    profile = CapabilityProfile.model_validate(
        yaml.safe_load((INPUTS / "profiles" / SCENARIO_PROFILES["full"]).read_text())
    )
    surface = determine_threat_surface(
        profile,
        load_risk_extraction(INPUTS / "risk-extractions/risk-extraction-fs-isac.json"),
        INPUTS / "mappings/risk_to_category.sssom.tsv",
        DATA_ROOT / "taxonomies/mappings/cross-taxonomy-mappings.yaml",
    )
    seeds = expand_seeds(surface)
    candidates = expand_candidates(seeds, profile, max_techniques=1)
    survivors, _, _ = apply_rule_based_filter(candidates, profile)
    surviving_ids = {c.candidate_id for c in survivors}
    threats = {}
    for seed in seeds:
        threat = threats.setdefault(
            seed.threat_id, {"id": seed.threat_id, "name": seed.threat_name, "seeds": []}
        )
        inputs = {}
        for c in candidates:
            if c.seed_id != seed.seed_id:
                continue
            branch = inputs.setdefault(
                c.entry_point_id,
                {
                    "id": c.entry_point_id,
                    "name": c.entry_point,
                    "controllability": c.controllability,
                    "direction": c.direction,
                    "candidate_count": 0,
                    "after_rules": 0,
                    "techniques": [],
                },
            )
            branch["candidate_count"] += 1
            branch["after_rules"] += c.candidate_id in surviving_ids
            branch["techniques"].extend(c.atlas_technique_ids)
        for branch in inputs.values():
            branch["techniques"] = sorted(set(branch["techniques"]))
        threat["seeds"].append(
            {"id": seed.seed_id, "name": seed.attack_pattern_name, "inputs": list(inputs.values())}
        )
    return {
        "policy": "FS-ISAC generative AI",
        "profile": "Full Klarna",
        "seed_count": len(seeds),
        "input_count": len({c.entry_point_id for c in candidates}),
        "candidate_count": len(candidates),
        "after_rules": len(survivors),
        "model_calls": 0,
        "threats": list(threats.values()),
    }
