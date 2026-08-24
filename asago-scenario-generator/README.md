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

`taxonomy-risk-demo.ipynb` defaults to the reviewed one-ingress Klarna canary,
coverage mode, one technique per scenario, and a one-scenario-per-pattern cap.
This is the recommended live notebook check. `stpa-demo.ipynb` defaults to
Klarna, two workers, bounded local numerical threads, and a fresh timestamped
output directory for each full SP1→SP3 run.

For STPA, direct endpoint variables are sufficient. To use a named model
profile instead, also set `ASAGO_STPA_PROFILE` and
`ASAGO_MODEL_PROFILES_FILE` to a populated, ignored profiles file.

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
