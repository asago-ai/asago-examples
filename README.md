# Asago Examples

Example notebooks and datasets for [Asago](https://github.com/asago-ai) projects.

## Available examples

| Folder | Description | Install group |
|--------|-------------|---------------|
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
