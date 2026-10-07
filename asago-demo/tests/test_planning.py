from asago_demo.planning import full_search_plan


def test_full_search_lists_real_seed_and_input_branches():
    plan = full_search_plan()
    seeds = [s for t in plan["threats"] for s in t["seeds"]]
    assert len(seeds) == plan["seed_count"]
    assert len({s["id"] for s in seeds}) == len(seeds)
    assert {s["id"] for s in seeds} >= {"AP-T5-01", "AP-T6-03", "AP-T10-01"}
    branches = [e for s in seeds for e in s["inputs"]]
    assert len({e["id"] for e in branches}) == plan["input_count"] == 3
    assert {e["controllability"] for e in branches} == {"direct", "indirect"}
    assert sum(e["candidate_count"] for e in branches) == plan["candidate_count"]
    assert all(e["direction"] in {"input", "bidirectional"} for e in branches)
    assert plan["model_calls"] == 0
