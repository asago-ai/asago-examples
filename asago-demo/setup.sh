#!/usr/bin/env bash
set -euo pipefail
demo_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$demo_dir/.." && pwd)"

uv sync --project "$repo_dir" --locked --extra demo
"$repo_dir/.venv/bin/python" "$demo_dir/prepare_report.py"
"$repo_dir/.venv/bin/python" -m ipykernel install --sys-prefix --name asago-demo --display-name "Asago demo"

# PR #11 runs in Python 3.13; the examples workspace uses Python 3.14.
if [[ ! -x "$demo_dir/.garak-venv/bin/python" ]]; then
  uv venv --no-project --python 3.13 "$demo_dir/.garak-venv"
fi
# The Garak pins have their own resolution date; do not inherit the workspace cutoff.
uv pip install --no-config --python "$demo_dir/.garak-venv/bin/python" -r "$demo_dir/garak-requirements.txt"
# This label identifies the local build; the immutable revision identifies its source.
SETUPTOOLS_SCM_PRETEND_VERSION=0.17.0.dev11 uv pip install \
  --no-config --python "$demo_dir/.garak-venv/bin/python" --no-deps \
  'garak @ git+https://github.com/trustyai-explainability/garak@06aba1a2c9b142d561eeeff08dfaffcbe77487c3'
printf '\nReady. Run ./asago-demo/launch.sh, then open http://127.0.0.1:8765\n'
