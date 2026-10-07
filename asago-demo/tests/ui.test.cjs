const test = require("node:test");
const assert = require("node:assert/strict");
const {
  chooseRunId,
  canRenderResult,
  resolveModel,
  activityView,
} = require("../view-state.js");

test("activity uses the execution clock and scope when rerunning a saved stage", () => {
  const run = {
    started: 1,
    status: "running",
    activity: {
      stage: "scenarios",
      stages: ["scenarios"],
      started: 100,
      status: "running",
      last_output_at: 120,
    },
    stages: {
      policy: { status: "completed", started: 1 },
      scenarios: { status: "running", started: 100 },
    },
  };
  const view = activityView(run, 180);
  assert.equal(view.elapsed, 80);
  assert.equal(view.quiet, 60);
  assert.deepEqual(view.stages, ["scenarios"]);
  run.activity.status = "failed";
  run.activity.ended = 150;
  assert.equal(activityView(run, 999).elapsed, 50);
  assert.equal(activityView(run, 999).quiet, null);
});

test("older saved runs still expose real pipeline steps and warnings", () => {
  const view = activityView(
    {
      status: "running",
      started: 1,
      stages: { scenarios: { started: 100, status: "running" } },
      logs: [
        "[Stage 3.5] Filtering candidates",
        "WARNING Request timed out — retrying",
      ],
    },
    180,
  );
  assert.match(view.phase, /Filtering/);
  assert.match(view.last_warning, /timed out/);
  assert.equal(view.stage, "scenarios");
  assert.equal(activityView(null), null);
});

test("an HTML response identifies a wrong demo server instead of a JSON syntax error", async () => {
  const { readAPIResponse } = require("../view-state.js");
  const response = new Response(
    "<!DOCTYPE HTML><title>Error response</title>",
    {
      status: 501,
      headers: { "Content-Type": "text/html" },
    },
  );
  await assert.rejects(() => readAPIResponse(response), /port.*another app/);
  assert.deepEqual(
    await readAPIResponse(
      new Response('{"models":["qwen"]}', {
        headers: { "Content-Type": "application/json" },
      }),
    ),
    { models: ["qwen"] },
  );
});

test("inherited roles follow the selected service and independent overrides", () => {
  const config = {
    scenario_provider: "ollama",
    model: "qwen:14b",
    artifact_provider: "same",
    artifact_model: "",
    judge_provider: "same",
    judge_model: "",
    target_provider: "litellm",
    target_model: "remote",
  };
  assert.deepEqual(resolveModel(config, "judge"), {
    provider: "ollama",
    model: "qwen:14b",
  });
  assert.deepEqual(resolveModel(config, "target"), {
    provider: "litellm",
    model: "remote",
  });
  config.artifact_provider = "litellm";
  config.artifact_model = "gemma";
  assert.deepEqual(resolveModel(config, "judge"), {
    provider: "litellm",
    model: "gemma",
  });
  config.judge_provider = "ollama";
  config.judge_model = "local-judge";
  assert.deepEqual(resolveModel(config, "judge"), {
    provider: "ollama",
    model: "local-judge",
  });
});

test("failed worker without a result payload keeps its error view", () => {
  assert.equal(
    canRenderResult("policy", {
      status: "failed",
      error: "Policy data missing",
    }),
    false,
  );
  assert.equal(
    canRenderResult("scenarios", {
      status: "failed",
      error: "Endpoint unavailable",
    }),
    false,
  );
  assert.equal(
    canRenderResult("artifact", {
      status: "failed",
      error: "No writable scenario",
    }),
    false,
  );
  assert.equal(
    canRenderResult("evaluation", {
      status: "failed",
      error: "Target unavailable",
    }),
    false,
  );
});

test("failure with useful diagnostics can still show its results", () => {
  assert.equal(
    canRenderResult("scenarios", {
      status: "failed",
      scenarios: [],
      quarantine: [{}],
    }),
    true,
  );
  assert.equal(
    canRenderResult("artifact", {
      status: "failed",
      artifact: {},
      validation: { ok: false },
    }),
    true,
  );
  assert.equal(
    canRenderResult("evaluation", {
      status: "failed",
      attempts: [],
      report_file: "run.jsonl",
    }),
    true,
  );
});

test("saved links stay pinned even when another live run starts or the snapshot is missing", () => {
  assert.equal(chooseRunId("saved-a", {active_id: "new-run", history: []}, null, "saved-a"), "saved-a");
  assert.equal(chooseRunId("", {active_id: "new-run", history: []}, null, "missing-snapshot"), "missing-snapshot");
  assert.equal(chooseRunId("saved-a", {run: {id: "saved-a", read_only: true}, active_id: "new-run"}, null), "saved-a");
});

test("new notebook runs become visible even when another run was selected", () => {
  assert.equal(
    chooseRunId("run-a", { active_id: "run-b", history: [] }, "run-a"),
    "run-b",
  );
  assert.equal(
    chooseRunId("run-a", { active_id: "run-b", history: [] }, null),
    "run-b",
  );
});

test("user can inspect history after active run has already been observed", () => {
  assert.equal(
    chooseRunId("run-a", { active_id: "run-b", history: [] }, "run-b"),
    "run-a",
  );
});

test("first connection opens the most recent saved run", () => {
  assert.equal(
    chooseRunId("", { active_id: null, history: [{ id: "latest" }] }, null),
    "latest",
  );
});


test("search tree renders every seed and escapes names", () => {
  const {renderSearchTree} = require("../view-state.js");
  const html = renderSearchTree({policy:"FS-ISAC",profile:"Klarna",threats:[{
    id:"T6",name:"<script>bad</script>",seeds:[{id:"AP-T6-03",name:"Poisoned retrieval",inputs:[{
      id:"retrieval",name:"RAG result",controllability:"indirect",candidate_count:2,after_rules:1,techniques:["AML.T0051"]
    }]},{id:"AP-T6-04",name:"Unsupported seed",inputs:[]}]
  }]});
  assert.ok(html.includes("AP-T6-03") && html.includes("AP-T6-04"));
  assert.ok(html.includes("RAG result") && html.includes("2 candidates · 1 after rules"));
  assert.ok(html.includes("Not expanded:"));
  assert.ok(!html.includes("<script>") && html.includes("&lt;script&gt;"));
});
