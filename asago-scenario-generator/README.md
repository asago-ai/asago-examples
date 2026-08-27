# Asago Scenario Generator examples

`taxonomy-risk-demo.ipynb` demonstrates the taxonomy/risk-driven (non-STPA)
workflow. `stpa-demo.ipynb` demonstrates the peer STPA workflow.

Install the scenario-generator workspace from the `asago-examples` repository
root:

```bash
uv sync --extra scenario-generator
```

Both notebooks fail before transmitting data unless either:

- `ASAGO_SCENARIO_GENERATOR_RUN_LIVE=1` explicitly enables model calls; or
- `ASAGO_EXISTING_RUN_DIR` points to existing output for inspection.

Configure the endpoint before launching Jupyter:

```bash
export ASAGO_SCENARIO_GENERATOR_MODEL_BASE_URL="https://your-endpoint.example/v1"
export ASAGO_SCENARIO_GENERATOR_MODEL_NAME="gemma-4-26b-a4b-it"
export ASAGO_SCENARIO_GENERATOR_API_KEY="none"
export ASAGO_SCENARIO_GENERATOR_RUN_LIVE="1"
uv run jupyter lab
```

The validated configuration uses named profiles from an ignored local file so
the endpoint and credentials never enter this repository:

```bash
export ASAGO_MODEL_PROFILE="gemma4-oc-taxonomy"
export ASAGO_STPA_PROFILE="gemma4-oc"
export ASAGO_MODEL_PROFILES_FILE="/absolute/path/to/config/model-profiles.yaml"
```

`taxonomy-risk-demo.ipynb` defaults to the reviewed one-ingress Klarna canary,
coverage mode, one technique per scenario, and a one-scenario-per-pattern cap.
This is the recommended live notebook check. `stpa-demo.ipynb` defaults to
Klarna, two workers, bounded local numerical threads, and a fresh timestamped
output directory for each full SP1→SP3 run.

For STPA, a named model profile is recommended because it keeps the complete
sampling configuration together. Named profile values take precedence over
environment sampling values. Direct environment configuration is equivalent
and supports `ASAGO_SCENARIO_GENERATOR_MAX_COMPLETION_TOKENS`,
`ASAGO_SCENARIO_GENERATOR_TEMPERATURE`, `ASAGO_SCENARIO_GENERATOR_TOP_P`,
`ASAGO_SCENARIO_GENERATOR_TOP_K`, and
`ASAGO_SCENARIO_GENERATOR_USE_GUIDED_DECODING`.

The STPA notebook emits a one-minute heartbeat while the synchronous pipeline
call is running. Recoverable normalization or merge diagnostics are displayed
as stage warnings; only `stage_errors` fail the notebook.

## Reproduce the validated exhaustive Klarna run

From this directory, first run the endpoint-free projection preflight. It
should report `"ready": true` before a long run:

```bash
uv run asago-scenario-generator projection-preflight \
  --use-case @inputs/use-cases/use-case-klarna-fs-isac-v36.txt \
  --risk-extraction inputs/risk-extractions/risk-extraction-fs-isac.json \
  --sssom inputs/mappings/risk_to_category.sssom.tsv \
  --profile inputs/profiles/klarna-capability-profile.yaml \
  --qualification-facts inputs/profiles/klarna-qualification-facts.yaml \
  --max-scenario-techniques 2
```

For an intentional exhaustive CLI run, configure the endpoint and start
generation:

```bash
export ASAGO_SCENARIO_GENERATOR_MODEL_BASE_URL="https://your-endpoint.example/v1"
export ASAGO_SCENARIO_GENERATOR_MODEL_NAME="gemma-4-26b-a4b-it"
export ASAGO_SCENARIO_GENERATOR_API_KEY="none"
export ASAGO_SCENARIO_GENERATOR_TEMPERATURE="0.4"

OMP_NUM_THREADS=1 \
OPENBLAS_NUM_THREADS=1 \
MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 \
uv run asago-scenario-generator generate \
  --use-case @inputs/use-cases/use-case-klarna-fs-isac-v36.txt \
  --risk-extraction inputs/risk-extractions/risk-extraction-fs-isac.json \
  --sssom inputs/mappings/risk_to_category.sssom.tsv \
  --output-dir output/taxonomy-risk \
  --profile inputs/profiles/klarna-capability-profile.yaml \
  --qualification-facts inputs/profiles/klarna-qualification-facts.yaml \
  --generation-mode exhaustive \
  --max-scenario-techniques 2
```

This is a full endpoint workload, not a smoke test. The reference run selected
115 candidates, made 505 model calls, and took about 2 hours 14 minutes. The
pipeline preserves admitted scenarios even when other candidates are
quarantined, and the CLI may return non-zero for such a terminal run.

Inspect the timestamped child directory under `output/taxonomy-risk/`:

- `finalization-inventory.json` is authoritative for attempted, admitted, and
  quarantined counts;
- `scenarios/` must contain one `.yaml` and one `.feature` per admission;
- `quarantine/` contains evidence for every non-admitted candidate;
- `coverage-gaps.json` describes remaining pattern coverage; and
- `run-manifest.yaml` records configuration and artifact receipts.

Do not infer success from process exit alone, and do not trust contradictory
zero-valued legacy manifest counters over the finalization inventory. The
notebook performs this reconciliation and displays quarantine violations by
owner and code.

The bundled Klarna use case, risk extraction, SSSOM mapping, reviewed capability
profile, and qualification facts match the inputs used by the validated full
run. Other bundled systems do not yet include reviewed profile/fact pairs and
may legitimately produce a much smaller corpus or no admissions.
