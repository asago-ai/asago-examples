import hashlib
import json
import re
import shutil

import pytest

from asago_demo.static_export import export_snapshot


def snapshot_fixture(tmp_path):
    source = tmp_path / "saved"
    source.mkdir()
    state = {
        "id": "saved-success",
        "status": "completed",
        "read_only": True,
        "stages": {
            s: {"status": "completed"} for s in ("policy", "scenarios", "artifact", "evaluation")
        },
    }
    (source / "state.json").write_text(json.dumps(state))
    for stage in state["stages"]:
        result = {"status": "completed"}
        if stage == "evaluation":
            result.update(outcome="attack_succeeded", response="propose refund 150")
        (source / f"{stage}.json").write_text(json.dumps(result))
    (source / "response.json").write_text('{"response":"propose refund 150"}')
    (source / "cache").mkdir()
    (source / "cache/private.json").write_text('{"api_key":"do-not-publish"}')
    (source / "settings.json").write_text('{"api_key":"do-not-publish"}')
    evidence = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in ("response.json", "cache/private.json")
    }
    (source / "snapshot-provenance.json").write_text(json.dumps({"evidence_sha256": evidence}))
    assets = {"patternfly.css": b"", "branding.css": b"", "logo.svg": b"<svg/>"}
    return source, assets


def test_static_export_preserves_results_and_excludes_unlisted_files_and_caches(tmp_path):
    source, assets = snapshot_fixture(tmp_path)
    before = (source / "response.json").read_bytes()
    output = tmp_path / "site"
    export_snapshot(source, output, assets)
    state = json.loads((output / "snapshot.json").read_text())
    assert state["run"]["id"] == "saved-success"
    assert state["run"]["results"]["evaluation"]["outcome"] == "attack_succeeded"
    assert state["settings"] == {}
    assert (output / "evidence/response.json").read_bytes() == before
    assert (source / "response.json").read_bytes() == before
    assert not (output / "evidence/cache").exists()
    assert not (output / "evidence/settings.json").exists()
    assert len(state["history"]) == 1


def test_static_export_rejects_changed_evidence_and_leaves_no_site(tmp_path):
    source, assets = snapshot_fixture(tmp_path)
    (source / "response.json").write_text("altered result")
    with pytest.raises(ValueError, match="hash"):
        export_snapshot(source, tmp_path / "site", assets)
    assert not (tmp_path / "site").exists()


@pytest.mark.parametrize("bad_path", ["../settings.json", "linked.json"])
def test_static_export_rejects_evidence_outside_snapshot(tmp_path, bad_path):
    source, assets = snapshot_fixture(tmp_path)
    outside = tmp_path / "settings.json"
    outside.write_text("private")
    (source / "linked.json").symlink_to(outside)
    (source / "snapshot-provenance.json").write_text(
        json.dumps(
            {"evidence_sha256": {bad_path: hashlib.sha256(outside.read_bytes()).hexdigest()}}
        )
    )
    with pytest.raises(ValueError, match="path|linked"):
        export_snapshot(source, tmp_path / "site", assets)


def test_static_export_requires_completed_read_only_snapshot(tmp_path):
    source, assets = snapshot_fixture(tmp_path)
    state = json.loads((source / "state.json").read_text())
    state["read_only"] = False
    (source / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="completed.*snapshot"):
        export_snapshot(source, tmp_path / "site", assets)


def test_updated_viewer_gets_a_new_script_url_to_bypass_browser_cache(tmp_path, monkeypatch):
    from asago_demo import static_export

    source, assets = snapshot_fixture(tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    for name in ("index.html", "app.js", "view-state.js", "style.css"):
        shutil.copyfile(static_export.ROOT / name, ui / name)
    monkeypatch.setattr(static_export, "ROOT", ui)
    export_snapshot(source, tmp_path / "before", assets)
    with (ui / "app.js").open("a") as script:
        script.write("\n// Updated viewer\n")
    export_snapshot(source, tmp_path / "after", assets)
    before = (tmp_path / "before/index.html").read_text()
    after = (tmp_path / "after/index.html").read_text()
    before_url = re.search(r'src="(\./app\.js[^\"]*)"', before).group(1)
    after_url = re.search(r'src="(\./app\.js[^\"]*)"', after).group(1)
    assert before_url != after_url
    assert (tmp_path / "after" / after_url.split("?")[0]).read_bytes() == (
        ui / "app.js"
    ).read_bytes()
