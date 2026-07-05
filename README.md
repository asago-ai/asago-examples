# Asago Examples

Example notebooks and datasets for [Asago](https://github.com/asago-ai) projects.

## Available examples

| Folder | Description | Install group |
|--------|-------------|---------------|
| [`asago-policy-mapper/`](./asago-policy-mapper/) | Risk extraction from policy documents | `policy-mapper` |

## Quickstart

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then pick the example you want to run:

```bash
uv sync --extra policy-mapper
```

This installs the sub-project and all its dependencies (including the upstream library from GitHub).

Then open the notebook:

```bash
jupyter notebook asago-policy-mapper/risk-extraction-demo.ipynb
```