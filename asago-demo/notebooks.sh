#!/usr/bin/env bash
set -euo pipefail
demo_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$demo_dir/.." && pwd)"
cd "$repo_dir"
exec "$repo_dir/.venv/bin/python" -m jupyterlab --notebook-dir="$demo_dir/notebooks" --no-browser
