# End-to-end Asago demo

A local dashboard and five notebooks connect saved policy evidence → live scenario
and artifact generation → a real model evaluation with Garak. The dashboard is
suited to a 3–5 minute screen recording and shares the same run controller as the
notebooks.

[**Open the precomputed successful-attack demo →**](https://MuneezaAzmat.github.io/asago-examples/demo/)
All four tabs and evidence links work in the browser without downloads, a local
server, credentials or inference. It shows the recorded Qwen `process_refund`
proposal for $150 and Garak's judgment; business tools were not executed.

The policy report's document name opens a local preview of all source PDF pages
in a new tab, with a download link for the original PDF. This works in embedded
browsers without native PDF support. The PDF and preview stay with each run;
viewing them needs no model call or external document service.

## Setup

Requires `uv`, Git, and download access. Supported on macOS and Linux. `uv` manages
the workspace's Python 3.14 and the separate Python 3.13 Garak environment.

From the repository root:

```bash
./asago-demo/setup.sh
cp asago-demo/.env.example asago-demo/.env
# Edit the endpoint, API key, and served model name in asago-demo/.env.
./asago-demo/launch.sh
```

Open **http://127.0.0.1:8765**. Keep the server running. Connection settings can
also be edited in the dashboard; saved credentials stay in an ignored local file.
The workspace root `.env` is supported, with `asago-demo/.env` taking precedence.

If another local app uses port 8765, run `./asago-demo/launch.sh --port 8766` and
open `http://127.0.0.1:8766` instead. In the notebooks use
`DemoClient(base_url="http://127.0.0.1:8766")`. An HTML response from the controller
API usually means the browser reached another server; this can also happen when
IPv4 and IPv6 listeners from different apps share the same port.

Open **Models & connections** to choose a service and model separately for scenario
generation, artifact generation, the Garak target, and the Garak judge. Each role
can use **LiteLLM**, **Ollama**, or **Google Gemini**. Artifact
generation initially inherits the scenario service/model, and the judge inherits
the artifact service/model; both can be overridden. Existing Gemma generation
and Qwen/Ollama target settings are preserved.

The panel loads model dropdowns from each service's `/models` endpoint. **Load
LiteLLM models** and **Load Ollama models** refresh them using the connection fields
currently in the panel. Listing models does not save settings or make an inference
request. If discovery is unavailable, choose **Enter a model name…**. Click **Save
model choices** to apply the selections to future runs. Active runs keep their
original configuration; settings are locked while a run is active.

LiteLLM retains its own base URL and API key. Ollama uses a separate base URL and
never receives the LiteLLM key; a bare Ollama server URL is normalized to `/v1`.
The default scenario model remains `gemma-4-26b`; use an actual served model name.
Each new stage records the model/service it used without credentials, so saved
results remain distinguishable from the next-run model choices.

For Gemini Flash and other Google models, enter your Google AI Studio key in
**Service connections → Google Gemini**, click **Load Google models**, select
**Google Gemini** for the desired roles and choose an available chat model. Then
click **Save model choices**. A model can also be entered manually. The demo uses
[Google's official OpenAI-compatible API](https://ai.google.dev/gemini-api/docs/openai)
directly, without a LiteLLM proxy. Its endpoint is fixed to Google. Set
`GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in the local environment as an alternative.
The Google key is separate from the LiteLLM key, never returned to the browser,
and redacted from logs, results and error messages. An empty key field preserves
the saved key. Model availability, quotas and supported request formats depend
on the Google account and selected model.

For evaluation, start [Ollama](https://ollama.com) and install a tool-capable Qwen
model, for example `ollama pull qwen2.5:14b`. The target defaults to
`http://127.0.0.1:11434/v1` and `qwen2.5:14b`. **Load Ollama models** lists installed
models. A tool-capable LiteLLM model can also be selected as the target. Tool
support in Garak PR #11 uses the OpenAI-compatible chat path.

## Four stages

1. **Policy Mapper:** load the saved FS-ISAC extraction already in this repository.
   No extraction model call is made. Explore the actual interactive report from
   [Policy Mapper PR #79](https://github.com/asago-ai/asago-policy-mapper/pull/79),
   including themes, taxonomy filters, grounding confidence, and evidence.
2. **Scenario Generator:** choose the entry-point profile, generation mode, and
   per-pattern limit on the page, then generate using this run's extraction.
   Inspect admitted/rejected scenario data,
   risk traceability, and behavior specifications; select a supported scenario.
3. **Artifact Generator:** generate and validate that scenario's conversation,
   tool-call context, and success/blocked rubric. Invalid artifacts stop the chain.
4. **Garak Evaluation:** replay the artifact against the selected target and judge the next model
   response with [Garak PR #11](https://github.com/trustyai-explainability/garak/pull/11).
   Inspect the actual response, proposed tool calls, judge confidence/reasoning,
   and downloadable native Garak JSONL evidence.

**Run demo** runs all four stages, choosing the first admitted scenario supported
by Garak. **Stop run** stops the active worker; duplicate jobs are rejected.
**Run activity** starts fresh each time you start a demo or individual stage; all
four stages stay together during **Run demo**. Completion details remain visible
until the next execution. The panel shows stage status, elapsed time, recorded
models and generation options, the latest pipeline step/output, warnings and
errors. Quiet periods show the time since the worker last printed output; they
are not estimates of model completion. Download the full execution log or open
**Earlier activity** for previous stage attempts. Older saved runs retain their
original logs. The run selector opens saved results.
Zero admitted scenarios, failed validation, and failed evaluations stay visible.
The UI calls drafts that failed generation or admission checks **Rejected scenarios**.
The underlying pipeline files retain their upstream `quarantine` field/path names.

### Presets and full search

The Scenario Generator has one search dropdown, used by both **Run scenarios**
and **Run demo**:

- **Preset – prompt injection** preserves the original working direct-input
  preset: T5 + T10, four seed patterns, exhaustive mode, one scenario per pattern.
- **Preset – indirect injection** uses a declared retrieval-response input and
  T6's seven seed patterns. The rules and canonical projection select eligible
  poisoned-tool-output candidates, capped at three scenarios for that pattern.
- **Full search** uses the full Klarna profile, exhaustive mode and one scenario
  per pattern. An expandable tree previews the actual installed catalog and
  FS-ISAC mappings: 24 seeds, three input entry points, 99 initial candidates and
  69 after deterministic rules with the current pins. It makes no model calls.
  Branches include their technique IDs and counts; model qualification,
  projection and admission can reduce the results further.

Presets change search options only. They preserve the selected providers, models,
credentials, target, judge and timeout. Choose those independently in
**Models & connections**. The previous profile/mode/variant controls are removed
from the webpage; the notebook configuration API still supports those options.
Recorded run settings remain separate from the next-run selection.

The prompt preset was verified with Gemini 3.1 Flash-Lite: three admitted
scenarios in 1:54 and 1:58. The indirect preset produced three admitted scenarios
and zero rejected scenarios in about 1:10, with a tool-response artifact passing
PR #8 validation. These are observed results, not count or speed guarantees.
Local model capacity, available memory and concurrency affect timing.

Provider-specific behavior is isolated in adapters. `generation.py` applies the
smaller behavior response schema and Flash-Lite pacing only to Google requests;
other providers retain the upstream response schema and have no Google pacing.
Ollama requests are serialized within a stage so local inference does not queue
several requests behind one another while their timeouts run. Shared actor/tree
guidance and filter length hints preserve canonical IDs and existing validation.
`evaluation.py` omits Gemini-incompatible request fields only for Google and
reports provider HTTP errors with the failing role/model instead of `NoneType`.
A Qwen2.5:14b target on Ollama with Gemini as judge completed in about 52 seconds.
Targets must support the artifact's tool schemas; Gemma2:2b rejects tool requests.
Qwen generation hit the 120-second request limit in a local trial; Ollama
generation speed is not yet validated to match the Gemini recording timings.

The indirect profile is an illustrative attacker-access assumption, not a claim
about Klarna's actual deployment. Its consuming zone is `reasoning`, while its
transport is a retrieval tool response. `artifact_context.py` maps that explicitly
declared, provenance-backed input to PR #8's legacy `(tool_execution)` surface tag
only in the in-memory artifact context. Admitted scenario YAML, canonical zones,
IDs and validation results remain intact. No rejected drafts are promoted.

The target receives replayed scenario context. Its proposed tool calls are
captured without executing business tools. Artifact validation is separate from
target evaluation. Garak's judge marks attack success at confidence ≥70/100;
a lower score means the full attack was not demonstrated, not general model
safety. Missing/invalid replies or judgments are inconclusive. Inspect the raw
response alongside the verdict: an individual concerning action can occur even
when a multi-part rubric is not fully satisfied.

## Notebooks

With the server running:

```bash
./asago-demo/notebooks.sh
```

Open Jupyter's displayed URL and choose the **Asago demo** kernel.

| Notebook | Purpose |
| --- | --- |
| `00-end-to-end.ipynb` | Complete staged walkthrough |
| `01-policy-mapper.ipynb` | Saved policy extraction and interactive report |
| `02-scenario-generator.ipynb` | Live scenarios and policy traceability |
| `03-artifact-generator.ipynb` | Live artifact generation and validation |
| `04-garak-evaluation.ipynb` | Real Qwen response and Garak judgment |

Run them in stage order. Notebook actions appear in the dashboard. Interrupting a
cell requests cancellation of that run/stage. The original component notebooks
remain in their existing folders.

## What is committed, and what is local

| Committed | Created locally and ignored |
| --- | --- |
| Python runner and browser UI | Workspace `.venv/` |
| Five notebooks with empty outputs | `asago-demo/.garak-venv/` |
| Tests, setup scripts, configuration example | `asago-demo/.cache/` report assets |
| Workspace lock and Garak dependency pins | `asago-demo/runs/` |
| This guide | `.env`, `settings.json`, notebook checkpoints |
| One reviewed successful snapshot and static viewer in `docs/demo/` | Other runs and investigation results |

Inputs are reused directly from `asago-policy-mapper/policy_examples/` and
`asago-scenario-generator/inputs/`. The single published snapshot is an explicit
exception to ignoring generated outputs; no repository clones, environments,
credentials, caches, or unrelated results are committed. The demo imports the artifact generator
installed by `uv`, without relying on a sibling development checkout.

| Component | Source |
| --- | --- |
| Scenario generator | Workspace lock; `c6a7355c2a3f18342d484f2f62901962b5e3baef` |
| Artifact generator | Workspace lock; `a7c586b7480ae8090019079c557e7c4842dd12f9` |
| Policy report | PR #79; `d2423c7bf12432f44fab6963f497dc7f975c7c26` |
| Garak probe/judge | PR #11; `06aba1a2c9b142d561eeeff08dfaffcbe77487c3` |

Setup caches only the reporting modules, mappings, templates, assets, and license
needed from Policy Mapper PR #79. Its full package requires Python <3.14, so the
workspace's extraction package remains at its existing lock revision. The report
adapter tolerates unavailable storage inside its isolated preview frame.

Garak is installed directly from its immutable Git revision into the separate
Python 3.13 environment. `garak-requirements.txt` records the resolved dependency
versions; `0.17.0.dev11` is a local build label, not an upstream release identifier.
The adapter converts artifact `turns` to OpenAI `messages`, removes ASAGO-only
annotations, serializes tool arguments, and preserves authored message content
and tool pairing. Tool schemas come from explicit artifact schemas when available,
otherwise from system-turn declarations. Unspecified parameter types remain
unrestricted. Context and success/blocked criteria are passed to InjectionJudge.

Each execution retains its native report under `runs/<run>/evaluation/`. Rerunning
an upstream stage invalidates downstream summaries while retaining raw evidence.
A server restart marks unfinished work interrupted and reopens the last used run.
Reports are isolated from the controller API; only localhost is served.

## Recording a 3–5 minute walkthrough

### Present a completed run without running models

Open the [published recording](https://MuneezaAzmat.github.io/asago-examples/demo/).
The four tabs, scenario filters, expandable evidence, PDF preview and downloads
stay interactive. The selected scenario is fixed to the saved artifact's source.
The page displays recorded model names and has no generation or connection controls.
There is no snapshot-creation button or API in the local dashboard. Existing
read-only local snapshots can still be viewed, with overwrite protection retained.

### Published recording

`docs/demo/` contains only snapshot `20261005-160555-saved-attack-success-cd0505`,
the successful evaluation `b51d45155c`, its selected artifact, the three scenarios
from that generation, and supporting policy/report/log evidence. It uses the same
UI renderers with fixed JSON data and relative file links. Live controls and API
polling are disabled; **Run your own demo** links to setup instructions.

The snapshot was assembled from the archived stage attempts identified in
`evidence/snapshot-provenance.json`; it is not a newly executed run.
`publication-manifest.json` records original and published hashes. Personal home
directory prefixes are replaced with `[local-home]`; scenario content, target
responses and judge results are preserved. Dependency caches are excluded.

The README preview is served by GitHub Pages on the contributor's fork, from
`codex/end-to-end-demo` → `/docs`. Only static files are served. A maintainer can
publish the same `/docs` directory from the upstream repository after merge and
update the README links. No deployment runs on pull-request events.

To reproduce an export after local setup, use a reviewed completed snapshot with
an explicit `snapshot-provenance.json` evidence manifest and a new output folder:

```bash
PYTHONPATH=asago-demo .venv/bin/python -m asago_demo.static_export \
  asago-demo/runs/<saved-run-id> /tmp/asago-demo-preview
```

Review the exported files before publishing; this is an explicit publication
step, not automatic uploading of local runs. The exporter verifies source hashes
and never changes the original snapshot. The bundled viewer needs only static
HTTP hosting; it does not require the Python controller or model endpoints.

### Record live generation

Use a wide browser window and **Recording view**. Show 20 seconds of context,
45 seconds of policy evidence, 60 seconds of scenarios, 60 seconds of artifacts,
and 60 seconds of evaluation. Finish with the target response, judge reasoning,
and downloadable evidence. Trim model waits while retaining a short view of real
progress. Keep the saved-policy label visible; opening an old result is not a
new model execution.

## Checks

After setup, from the repository root:

```bash
.venv/bin/python -m pytest asago-demo/tests -q
PYTHONPATH=asago-demo asago-demo/.garak-venv/bin/python -m pytest asago-demo/tests/test_garak_integration.py -q
.venv/bin/ruff check asago-demo
.venv/bin/ruff format --check asago-demo
node --test asago-demo/tests/ui.test.cjs
```

These checks make no model calls. The PR-specific integration test runs in the
Garak environment; it is skipped when Garak is not installed. Live verification
requires configured generation/judge credentials and a running Ollama model.
