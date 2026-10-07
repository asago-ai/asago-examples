"""Cache only the reporting files from Policy Mapper PR #79, outside Git."""

import io
import shutil
import ssl
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

import certifi

REVISION = "d2423c7bf12432f44fab6963f497dc7f975c7c26"
ROOT = Path(__file__).resolve().parent
PACKAGE = "src/asago_policy_mapper/"
FILES = {
    "LICENSE",
    PACKAGE + "extract/report.py",
    PACKAGE + "extract/report_themes.py",
    PACKAGE + "data/risk_to_category.sssom.tsv",
    PACKAGE + "data/report_themes.yaml",
}


def prepare():
    cache = ROOT / ".cache"
    target = cache / "policy-report"
    marker = target / ".revision"
    if (
        marker.exists()
        and marker.read_text().strip() == REVISION
        and all((target / name).is_file() for name in FILES)
    ):
        print("Policy report cache is ready.")
        return
    cache.mkdir(exist_ok=True)
    url = f"https://api.github.com/repos/asago-ai/asago-policy-mapper/tarball/{REVISION}"
    request = urllib.request.Request(url, headers={"User-Agent": "asago-examples-demo"})
    print("Downloading pinned Policy Mapper report assets…", flush=True)
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        archive = response.read()
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        stage = Path(temporary) / "report"
        stage.mkdir()
        copied = set()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
            for member in source:
                parts = PurePosixPath(member.name).parts[1:]
                relative = PurePosixPath(*parts)
                name = str(relative)
                if not member.isfile() or ".." in parts:
                    continue
                if name not in FILES and not name.startswith(PACKAGE + "templates/"):
                    continue
                output = stage / name
                output.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as input_file:
                    output.write_bytes(input_file.read())
                copied.add(name)
        if not FILES <= copied or not any("templates/" in path for path in copied):
            raise RuntimeError("Pinned archive is missing required report files")
        (stage / ".revision").write_text(REVISION + "\n")
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    print("Policy report assets cached; no repository clone is needed.")


if __name__ == "__main__":
    prepare()
