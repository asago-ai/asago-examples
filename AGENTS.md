# Asago Examples

A collection of sub-projects demonstrating how to use parts of the Asago platform.

## Repo structure

Each top-level folder is a self-contained sub-project with its own `pyproject.toml`, dependencies, and example notebooks/scripts. The root `pyproject.toml` exposes each sub-project as an optional dependency group so users can install only what they need.

Sub-project package names use the `-examples` suffix (e.g. `asago-policy-mapper-examples`) to avoid colliding with the upstream library they depend on.

```
asago-examples/
├── pyproject.toml              # root project; optional deps point to sub-projects
├── asago-policy-mapper/        # examples for the policy mapper library
│   ├── pyproject.toml          # sub-project deps (installs asago-policy-mapper from GitHub)
│   ├── policy_examples/        # sample policy documents (PDF, Markdown, DOCX)
│   └── risk-extraction-demo.ipynb
└── ...                         # future sub-projects follow the same pattern
```

## Adding a new sub-project

1. Create a folder at the repo root (e.g. `asago-new-tool/`).
2. Add a `pyproject.toml` in that folder. Use a `-examples` suffix for the package name to avoid colliding with the upstream library:
   ```toml
   [project]
   name = "asago-new-tool-examples"
   dependencies = [
       "asago-new-tool @ git+https://github.com/asago-ai/asago-new-tool",
   ]
   ```
3. Register it in the root `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   new-tool = ["asago-new-tool-examples"]

   [tool.uv.sources]
   asago-new-tool-examples = { path = "./asago-new-tool" }
   ```
4. Add notebooks, scripts, and sample data inside the folder.