import pytest

from asago_demo.runtime import STAGES, Coordinator, Settings, atomic_json


def saved_run(root, run_id="saved"):
    folder = root / "runs" / run_id
    folder.mkdir(parents=True)
    state = {
        "id": run_id,
        "status": "completed",
        "read_only": True,
        "snapshot": {"source_run_id": "original"},
        "started": 100,
        "model": "original-model",
        "stages": {s: {"status": "completed"} for s in STAGES},
    }
    atomic_json(folder / "state.json", state)
    for stage in STAGES:
        atomic_json(folder / f"{stage}.json", {"status": "completed", "evidence": stage})
    (folder / "policy").mkdir()
    (folder / "policy/report.html").write_text("Original report")
    return folder


@pytest.mark.parametrize("stage", [*STAGES, "all"])
def test_existing_read_only_evidence_cannot_be_overwritten(tmp_path, stage):
    folder = saved_run(tmp_path)
    before = (folder / "state.json").read_bytes()
    coordinator = Coordinator(tmp_path, Settings(tmp_path, defaults={}))
    assert coordinator.active_id is None
    with pytest.raises(ValueError, match="read-only"):
        coordinator.start(stage, "saved")
    assert not coordinator.busy
    assert (folder / "state.json").read_bytes() == before


def test_implicit_active_snapshot_cannot_be_overwritten(tmp_path):
    saved_run(tmp_path)
    coordinator = Coordinator(tmp_path, Settings(tmp_path, defaults={}))
    coordinator.active_id = "saved"
    with pytest.raises(ValueError, match="read-only"):
        coordinator.start("scenarios")
