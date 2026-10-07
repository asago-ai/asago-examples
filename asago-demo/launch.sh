#!/usr/bin/env bash
set -euo pipefail
demo_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$demo_dir/.." && pwd)"
if [[ ! -x "$repo_dir/.venv/bin/python" || ! -f "$demo_dir/.cache/policy-report/.revision" ]]; then
  echo "Run ./asago-demo/setup.sh first."
  exit 1
fi
cd "$repo_dir"
exec "$repo_dir/.venv/bin/python" -m asago_demo.server "$@"
