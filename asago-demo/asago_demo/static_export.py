"""Publish one reviewed saved snapshot using the existing dashboard renderers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("policy", "scenarios", "artifact", "evaluation")
GUIDE = (
    "https://github.com/MuneezaAzmat/asago-examples/"
    "blob/codex/end-to-end-demo/asago-demo/README.md"
)


def export_snapshot(source: Path, output: Path, assets: dict[str, bytes]) -> dict:
    """Export only manifest-listed evidence and four completed stage summaries.

    Caches are excluded. Source hashes are verified before any output is written.
    Personal home-directory prefixes are removed from published text; model
    replies, judgments and scenario/artifact content are otherwise unchanged.
    """
    source = source.resolve()
    if output.exists():
        raise ValueError("Choose a new output directory; existing exports are not overwritten")

    def read(name):
        path = source / name
        if path.is_symlink() or source not in path.resolve().parents:
            raise ValueError(f"Unsafe or linked evidence path: {name}")
        if any(p.is_symlink() for p in path.parents if p != source and source in p.parents):
            raise ValueError(f"Unsafe linked evidence path: {name}")
        return path.read_bytes()

    state = json.loads(read("state.json"))
    state["results"] = {stage: json.loads(read(f"{stage}.json")) for stage in STAGES}
    if (
        not state.get("read_only")
        or state.get("status") != "completed"
        or any(
            state.get("stages", {}).get(stage, {}).get("status") != "completed"
            or state["results"][stage].get("status") != "completed"
            for stage in STAGES
        )
    ):
        raise ValueError("A completed read-only snapshot is required")
    provenance = json.loads(read("snapshot-provenance.json"))
    files = {}
    for name, expected in provenance["evidence_sha256"].items():
        if "cache" in Path(name).parts:
            continue
        data = read(name)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Evidence hash mismatch: {name}")
        files[name] = data
    for name in ("state.json", "snapshot-provenance.json", *(f"{s}.json" for s in STAGES)):
        files[name] = read(name)

    def public_bytes(data):
        text = data.decode("utf-8")
        # Keep local paths useful for provenance without publishing a personal username.
        return re.sub(r"/(?:Users|home)/[^/\s\"<>\\]+", "[local-home]", text).encode()

    snapshot = {
        "run": state,
        "history": [{"id": state["id"], "status": "completed", "read_only": True}],
        "busy": False,
        "active_id": state["id"],
        "settings": {},
    }
    payloads = {}
    manifest = {
        "snapshot_id": state["id"],
        "source_evidence": "evidence/snapshot-provenance.json",
        "note": "Only this saved demo is published. Caches are excluded. Personal home-directory "
        "prefixes are replaced with [local-home]; recorded model results are unchanged.",
        "files": {},
    }
    for name, data in files.items():
        published = data if Path(name).suffix == ".pdf" else public_bytes(data)
        payloads["evidence/" + name] = published
        manifest["files"][name] = {
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "published_sha256": hashlib.sha256(published).hexdigest(),
            "local_paths_redacted": data != published,
        }
    payloads["snapshot.json"] = public_bytes(json.dumps(snapshot, ensure_ascii=False).encode())
    config = {"runId": state["id"], "stateURL": "snapshot.json", "filesBase": "evidence/"}
    payloads["static-demo.js"] = (
        "window.AsagoStaticDemo = " + json.dumps(config) + ";\n"
    ).encode()
    for name in ("app.js", "view-state.js", "style.css"):
        payloads[name] = (ROOT / name).read_bytes()
    html = (ROOT / "index.html").read_text()
    html = html.replace('href="/', 'href="./').replace('src="/', 'src="./')
    html = html.replace(
        '<script src="./view-state.js"',
        '<script src="./static-demo.js" defer></script>\n    <script src="./view-state.js"',
    )
    # GitHub Pages caches scripts. A content version makes a newly exported page
    # request the matching viewer instead of reusing an earlier deployment.
    version = hashlib.sha256(payloads["app.js"]).hexdigest()[:12]
    html = html.replace('src="./app.js"', f'src="./app.js?v={version}"')
    html = html.replace(
        '<a href="./">Return to live demo ↗</a>',
        f'<a href="{GUIDE}" target="_blank" rel="noreferrer">Run your own demo ↗</a>',
    )
    # A static host has no response-header configuration; limit this page to local assets.
    html = html.replace(
        '<meta charset="utf-8" />',
        '<meta charset="utf-8" />\n    <meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; "
        "object-src 'none'; base-uri 'none'\" />",
    )
    payloads["index.html"] = html.encode()
    payloads.update({"assets/" + name: data for name, data in assets.items()})
    payloads["publication-manifest.json"] = json.dumps(manifest, indent=2).encode()
    for name, data in payloads.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "snapshot", type=Path, help="Reviewed snapshot with snapshot-provenance.json"
    )
    parser.add_argument("output", type=Path, help="New static-site directory")
    args = parser.parse_args()
    from asago_demo.reporting import PR_PACKAGE, report_module

    templates = PR_PACKAGE / "templates"
    css, _, notices = report_module()._browser_assets()
    branding = (
        (templates / "report_branding.html")
        .read_text()
        .split("<style>", 1)[1]
        .split("</style>", 1)[0]
    )
    assets = {
        "patternfly.css": css.encode(),
        "branding.css": branding.encode(),
        "logo.svg": (templates / "assets/asago-main-logo-dark.svg").read_bytes(),
        "THIRD-PARTY-NOTICES.txt": notices.encode(),
        "POLICY-MAPPER-LICENSE.txt": (PR_PACKAGE.parents[1] / "LICENSE").read_bytes(),
    }
    manifest = export_snapshot(args.snapshot, args.output, assets)
    print(f"Exported {manifest['snapshot_id']}: {len(manifest['files'])} evidence files")


if __name__ == "__main__":
    main()
