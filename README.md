# Asago Examples

Example notebooks and datasets for [Asago](https://github.com/asago-ai) projects.

## Available examples

| Folder | Description | Install group |
|--------|-------------|---------------|
| [`asago-demo/`](./asago-demo/) | Four-stage dashboard and notebooks: policy → scenarios → artifacts → Garak evaluation | `demo` |
| [`asago-policy-mapper/`](./asago-policy-mapper/) | Risk extraction from policy documents | `policy-mapper` |
| [`asago-artifact-generator/`](./asago-artifact-generator/) | Garak probe artifacts from scenario YAMLs | `artifact-generator` |
| [`asago-scenario-generator/`](./asago-scenario-generator/) | Adversarial scenario generation (taxonomy/risk and STPA) | `scenario-generator` |

## Quickstart

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then pick the example you want to run:

```bash
uv sync --extra policy-mapper          # risk extraction
uv sync --extra scenario-generator     # scenario generation
```

This installs the sub-project and all its dependencies (including the upstream library from GitHub).

Then open a notebook:

```bash
jupyter notebook asago-policy-mapper/risk-extraction-demo.ipynb
jupyter notebook asago-scenario-generator/taxonomy-risk-demo.ipynb   # taxonomy/risk pipeline
jupyter notebook asago-scenario-generator/stpa-demo.ipynb            # STPA pipeline
```

## Recordable end-to-end demo

[**Open the precomputed demo in your browser →**](https://MuneezaAzmat.github.io/asago-examples/demo/)

No downloads, setup, API keys, or live model calls are needed. This is the same
saved successful-attack demo: explore the policy report, three indirect-injection
scenarios, the selected artifact, and the recorded Qwen/Garak result. Qwen proposed
a $150 refund; business tools were not executed. Only this snapshot and its
supporting evidence are published. The preview is hosted from this PR's branch
on the contributor's GitHub Pages site.

To run your own demo locally:

Run `./asago-demo/setup.sh`, configure `asago-demo/.env`, and start
`./asago-demo/launch.sh`. Open **http://127.0.0.1:8765** for the interactive
four-stage dashboard. It reuses the saved FS-ISAC extraction and Klarna inputs,
generates scenarios and artifacts, then evaluates the artifact using Garak.
**Models & connections** selects LiteLLM or Ollama models independently for each
step, with Qwen on local Ollama as the default target. See the [demo guide](./asago-demo/README.md) for notebooks,
endpoint settings, dependency pins, checks, and a recording outline.
