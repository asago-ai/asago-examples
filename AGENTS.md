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