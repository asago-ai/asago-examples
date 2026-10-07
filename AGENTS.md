# Asago Examples

A collection of sub-projects demonstrating how to use parts of the Asago platform.

## Repo structure

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/). Each `asago-*` folder is a workspace member with its own `pyproject.toml` and dependencies. The root `pyproject.toml` exposes each member as an optional dependency group so users can install only what they need.

Sub-project package names use the `-examples` suffix (e.g. `asago-policy-mapper-examples`) to avoid colliding with the upstream library they depend on. Python version is set only in the root `pyproject.toml` — members inherit it via the workspace.

```
asago-examples/
├── pyproject.toml              # workspace root; optional deps + [tool.uv.workspace]
├── asago-policy-mapper/        # examples for the policy mapper library
│   ├── pyproject.toml          # member deps (installs asago-policy-mapper from GitHub)
│   ├── policy_examples/        # sample policy documents (PDF, Markdown, DOCX)
│   └── risk-extraction-demo.ipynb
├── asago-scenario-generator/   # taxonomy/risk and STPA scenario generation
│   ├── pyproject.toml
│   ├── inputs/                 # use cases, risk extractions, SSSOM, reviewed profiles
│   ├── taxonomy-risk-demo.ipynb
│   └── stpa-demo.ipynb
└── ...                         # future members are auto-discovered via "asago-*" glob
```

## Adding a new sub-project

1. Create a folder at the repo root matching the `asago-*` glob (e.g. `asago-new-tool/`). It will be auto-discovered as a workspace member.
2. Add a `pyproject.toml` in that folder. Use a `-examples` suffix for the package name to avoid colliding with the upstream library. Do not set `requires-python` — it's inherited from the root.
   ```toml
   [project]
   name = "asago-new-tool-examples"
   version = "0.1.0"
   dependencies = [
       "asago-new-tool @ git+https://github.com/asago-ai/asago-new-tool",
   ]
   ```
3. Register it in the root `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   new-tool = ["asago-new-tool-examples"]

   [tool.uv.sources]
   asago-new-tool-examples = { workspace = true }
   ```
4. Add notebooks, scripts, and sample data inside the folder.

## End-to-end demo

`asago-demo/` is the `demo` optional install group. Its `asago_demo` package owns
the localhost controller and four stage workers; static assets and notebooks live
beside it. Reuse existing component input directories and installed libraries.
Do not commit environments, dependency caches, credentials, notebook outputs, or
unreviewed run results. The one reviewed successful snapshot in `docs/demo/` is
an explicitly approved publication; keep all other generated runs ignored.
`./asago-demo/setup.sh` installs the locked workspace, fetches only
the pinned policy report files, and prepares the separate Python 3.13 Garak
environment. Keep PR dependency revisions explicit until the features are released.
Scenario options are validated by `asago_demo.runtime`, applied by the worker,
and recorded in each scenario stage's `generation_options`. Keep saved-run labels
separate from the dashboard's next-run settings.
`model_connection` resolves each role's LiteLLM/Ollama/Google service and credentials;
all workers and Garak clients must use it. Model discovery previews draft
connections without saving them. Never forward the LiteLLM key to Ollama, and
record only public connection details in stage state.
Keep the policy report header focused on the linked document name. Only the
policy report with its adjacent source PDF may open a new tab outside its sandbox;
all reports remain isolated from the controller API.
Google Gemini uses its fixed official compatibility endpoint and a separate
`google_api_key` (GEMINI_API_KEY/GOOGLE_API_KEY). Include every secret field in
public-state filtering, empty-key preservation and redaction. Never send the
Google key to LiteLLM/Ollama or accept a custom Google discovery endpoint.
Each start creates fresh `activity` metadata and a separate execution log. Retain
`logs` as the latest 160 lines for notebook compatibility; archive earlier attempts
in `activity_history`. A full demo shares one activity record across all stages.
Keep completion, cancellation, failure and restart states consistent with activity.
Scenario presets use a reduced threat input through the pipeline's public
`threats_path` argument before seed expansion; never bypass qualification or
validation. Prompt injection preserves T5 + T10, direct input, exhaustive mode,
one scenario per pattern. Indirect injection uses T6, the declared retrieval
profile, and up to three scenarios per pattern. Guard the installed pattern IDs.
`SCENARIO_PRESETS` changes search options only; preserve providers and model settings.
The webpage shows two presets and Full search, with a read-only cached search tree
built by `planning.py` from the same profile, saved extraction and installed catalog.
Keep Google response-schema limits/pacing in `generation.py`, and Google request
parameter suppression in `evaluation.py`; other providers must not inherit these.
Serialize Ollama scenario calls in the generation adapter to avoid local request
queue contention; do not impose Google pacing or schemas on Ollama.
The worker-scoped bridge guides actor/tree drafts without rewriting generated
actors or changing admission. `artifact_context.py` translates only the declared,
provenance-backed retrieval carrier into the pinned generator's legacy surface tag;
never change admitted scenario files to force a tool-return classification.
Remove compatibility bridges when equivalent upstream fixes are pinned.
The published demo uses fixed snapshot files; there is no snapshot-creation API.
The `/?saved=<id>` view must stay pinned, use recorded model metadata, hide live
controls, and preserve scenario-to-artifact provenance. Enforce the execution
guard in the coordinator as well as the UI. Local snapshots stay ignored. The
static exporter publishes only manifest-listed evidence from one reviewed
completed snapshot, excludes caches and records source/published hashes. Reuse
the existing result renderers; published pages must never call the controller
API or model endpoints. Keep all evidence links relative for GitHub Pages paths.

Checks: `.venv/bin/python -m pytest asago-demo/tests -q`,
`.venv/bin/ruff check asago-demo`, `.venv/bin/ruff format --check asago-demo`, and
`node --test asago-demo/tests/ui.test.cjs`. Run Garak adapter checks with
`PYTHONPATH=asago-demo asago-demo/.garak-venv/bin/python -m pytest asago-demo/tests/test_garak_integration.py -q`.
