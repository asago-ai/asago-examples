/* Local controller; all model text is escaped before insertion. */
const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const staticDemo = window.AsagoStaticDemo;
const pinnedRun = staticDemo?.runId || new URLSearchParams(window.location.search).get("saved") || "";
let selectedRun = pinnedRun,
  activeTab = "policy",
  snapshot = null,
  renderKey = "",
  selectedScenario = "",
  pending = false;
let scenarioSearch = "",
  surfaceFilter = "";
let observedActiveId = null;
let scenarioOptionsDirty = false;
const { chooseRunId, canRenderResult, resolveModel, activityView } =
  window.AsagoViewState;
let observedActivity = "";
const names = {
  policy: "Policy Mapper",
  scenarios: "Scenario Generator",
  artifact: "Artifact Generator",
  evaluation: "Garak Evaluation",
};
const titles = {
  policy: "Policy findings",
  scenarios: "Adversarial scenarios",
  artifact: "Garak test artifact",
  evaluation: "Garak evaluation results",
};
const descriptions = {
  policy:
    "Saved FS-ISAC extraction · Explore evidence, themes, and grounded risk matches.",
  scenarios:
    "Live generation · Turn policy risks and the Klarna use case into testable scenarios.",
  artifact:
    "Live generation · Inspect the attack transcript, detector rubric, and validation evidence.",
  evaluation:
    "Live evaluation · Replay the artifact against the selected target and inspect Garak’s judgment.",
};
const savedDescriptions = {
  ...descriptions,
  scenarios: "Saved scenarios · Explore the admitted scenarios, policy evidence, and behavior specifications.",
  artifact: "Saved artifact · Inspect the generated transcript, detector rubric, and validation evidence.",
  evaluation: "Saved evaluation · Inspect the recorded target response and Garak’s judgment.",
};
function isSavedDemo() {
  return !!pinnedRun || !!snapshot?.run?.read_only;
}

async function api(route, data) {
  if (data !== undefined && isSavedDemo())
    throw new Error("This saved demo is read-only. Open the live demo to start a run.");
  if (staticDemo && (data !== undefined || !route.startsWith("/api/state")))
    throw new Error("This published demo only contains saved results.");
  const response = await fetch(
    staticDemo ? staticDemo.stateURL : route,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Asago-Demo": "1" },
          body: JSON.stringify(data),
        },
  );
  const result = await window.AsagoViewState.readAPIResponse(response);
  if (!response.ok) throw new Error(result.error || "The request failed.");
  return result;
}
function notice(text) {
  $("#notice").textContent = displayMessage(text);
  $("#notice").hidden = !text;
}
function displayMessage(text) {
  return String(text || "")
    .replace(/\bquarantined\b/gi, "rejected")
    .replace(/Inspect quarantine/g, "Inspect rejected scenarios");
}
function fileURL(path) {
  if (staticDemo)
    return staticDemo.filesBase + path.split("/").map(encodeURIComponent).join("/");
  return (
    "/files/" +
    [selectedRun, ...path.split("/")].map(encodeURIComponent).join("/")
  );
}
function download(path, label) {
  return path
    ? `<a href="${escapeHTML(fileURL(path))}" target="_blank" rel="noreferrer">${escapeHTML(label)}</a>`
    : "";
}
function code(value) {
  return `<pre class="code">${escapeHTML(typeof value === "string" ? value : JSON.stringify(value, null, 2))}</pre>`;
}
function metric(value, label, mint = false) {
  return `<div class="metric ${mint ? "mint" : ""}"><strong>${escapeHTML(value)}</strong><span>${escapeHTML(label)}</span></div>`;
}
function empty(title, text, number = "→") {
  return `<div class="empty"><span class="empty-number">${number}</span><h3>${escapeHTML(title)}</h3><p>${escapeHTML(text)}</p></div>`;
}

function selectTab(tab) {
  activeTab = tab;
  renderKey = "";
  document.querySelectorAll("[data-tab]").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tab);
    el.setAttribute("aria-selected", el.dataset.tab === tab);
  });
  $("#panel-kicker").textContent =
    `${{ policy: "01", scenarios: "02", artifact: "03", evaluation: "04" }[tab]} / ${names[tab].toUpperCase()}`;
  $("#panel-title").textContent = titles[tab];
  $("#panel-description").textContent = descriptions[tab];
  render();
}

function controls() {
  const run = snapshot?.run,
    frozen = isSavedDemo(),
    busy = (!frozen && snapshot?.busy) || pending;
  for (const id of ["run-all", "run-stage", "settings-open"])
    $("#" + id).hidden = frozen;
  $("#saved-demo").hidden = !frozen;
  $("#saved-demo-detail").textContent = run?.snapshot
    ? `Snapshot saved ${new Date(run.snapshot.captured_at * 1000).toLocaleString()} · Source run ${run.snapshot.source_run_id}`
    : "Loading saved results…";
  $("#panel-description").textContent = (frozen ? savedDescriptions : descriptions)[activeTab];
  $("#run-all").disabled = !!busy;
  $("#cancel").hidden = frozen || !snapshot?.busy;
  $("#history").disabled = frozen || !!busy;
  $("#settings-open").disabled = !!busy;
  renderScenarioOptions(busy);
  const roles =
    {
      scenarios: ["scenario"],
      artifact: ["artifact"],
      evaluation: ["target", "judge"],
    }[activeTab] || [];
  const recordedModels = run?.stages?.[activeTab]?.models;
  $("#stage-model-summary").hidden = !roles.length;
  $("#stage-model-summary").textContent =
    (frozen ? "Recorded run: " : recordedModels ? "This run: " : "Next run: ") +
    roles
      .map((role) => {
        const choice =
          recordedModels?.[role] ||
          (frozen ? {provider: "", model: "Not recorded"} : resolveModel(snapshot?.settings || {}, role));
        return `${role === "target" ? "Target" : role === "judge" ? "Judge" : "Model"}: ${serviceName(choice.provider)} · ${choice.model || "Choose model"}`;
      })
      .join(" / ");
  const info = run?.stages?.[activeTab];
  const upstream = {
    scenarios: "policy",
    artifact: "scenarios",
    evaluation: "artifact",
  }[activeTab];
  const prerequisite =
    !upstream || run?.stages?.[upstream]?.status === "completed";
  $("#run-stage").disabled = !!busy || !prerequisite;
  $("#run-stage").textContent = {
    policy: "Load saved policy",
    scenarios: "Run scenarios",
    artifact: "Generate artifact",
    evaluation: "Run Garak evaluation",
  }[activeTab];
  $("#elapsed").textContent = info?.started
    ? formatTime((info.ended || Date.now() / 1000) - info.started)
    : "";
  for (const stage of Object.keys(names)) {
    const status = run?.stages?.[stage]?.status || "pending";
    const el = document.querySelector(`[data-tab="${stage}"]`);
    el.dataset.status = status;
    $(`#${stage}-status`).textContent =
      stage === "policy" && status === "completed"
        ? "Saved results loaded"
        : status === "pending"
          ? "Waiting"
          : status;
  }
}
function readScenarioOptions() {
  const scope = $("#scenario-scope").value;
  const config = scope === "full" ? snapshot.full_search_options : snapshot.scenario_presets[scope];
  return Object.fromEntries(["scenario_scope", "scenario_profile", "generation_mode", "max_scenarios_per_pattern"].map(key => [key, config[key]]));
}
let searchPlanLoaded = false;
let searchPlanLoading = false;
async function loadSearchPlan() {
  if (searchPlanLoaded || searchPlanLoading) return;
  searchPlanLoading = true;
  try {
    const plan = await api("/api/search-plan");
    $("#search-plan-summary").textContent = `${plan.seed_count} seeds · ${plan.input_count} inputs · ${plan.candidate_count} initial candidates · ${plan.after_rules} after rules`;
    $("#search-tree").innerHTML = window.AsagoViewState.renderSearchTree(plan);
    searchPlanLoaded = true;
  } catch (error) {
    $("#search-plan-summary").textContent = `Could not load the search tree: ${error.message}`;
  } finally { searchPlanLoading = false; }
}
function renderScenarioOptions(busy) {
  $("#scenario-options").hidden = isSavedDemo() || activeTab !== "scenarios";
  if (isSavedDemo()) return;
  if (!snapshot?.settings) return;
  if (!scenarioOptionsDirty) {
    const scope = snapshot.settings.scenario_scope || "recording";
    $("#scenario-scope").value = scope === "quick3" ? "recording" : scope;
  }
  $("#scenario-scope").disabled = !!busy;
  const options = readScenarioOptions();
  const full = options.scenario_scope === "full";
  const indirect = options.scenario_scope === "indirect";
  $("#scope-help").textContent = full
    ? "Explore eligible attack patterns across user messages, retrieved knowledge and customer context."
    : indirect
      ? "Poisoned retrieval responses: up to 3 scenarios, with qualification and validation enabled."
      : "The existing direct-input preset: 4 fixed patterns, with qualification and validation enabled.";
  $("#generation-expectation").textContent = full
    ? "Full search makes more model calls and takes longer than a preset."
    : "Final scenario counts depend on qualification and validation.";
  $("#search-plan").hidden = !full;
  if (full && activeTab === "scenarios") loadSearchPlan();
  const stage = snapshot.run?.stages?.scenarios;
  const recorded = stage?.generation_options;
  const label = $("#run-generation-options");
  label.hidden = !stage || stage.status === "pending";
  label.textContent = recorded
    ? `${stage.status === "running" ? "Running with" : "Displayed run used"}: ${scopeLabel(recorded.scenario_scope)} / ${profileLabel(recorded.scenario_profile)} / ${recorded.generation_mode} / per-pattern limit ${recorded.max_scenarios_per_pattern}.`
    : "This saved run predates option tracking; its generation settings were not recorded.";
}
function scopeLabel(scope) {
  return {recording: "Preset – prompt injection", indirect: "Preset – indirect injection", quick3: "Legacy quick demo", full: "Full search"}[scope] || scope;
}
function profileLabel(profile) {
  return {direct: "Direct input · 1 entry point", indirect: "Retrieval response · 1 indirect entry point", full: "Full Klarna · 3 inputs"}[profile] || profile;
}
$("#expand-search-tree").addEventListener("click", () => {
  const nodes = [...$("#search-tree").querySelectorAll("details")];
  const expand = nodes.some(node => !node.open);
  nodes.forEach(node => { node.open = expand; });
  $("#expand-search-tree").textContent = expand ? "Collapse seeds" : "Expand all seeds";
});

function formatTime(seconds) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

function activityMessage(line) {
  return displayMessage(line).replace(
    /^\d{4}-\d{2}-\d{2}T\S+\s+\w+\s+\[[^\]]+\]\s*/,
    "",
  );
}
function renderActivity() {
  const run = snapshot?.run,
    activity = activityView(run);
  $("#activity-details").hidden = !activity;
  $("#live-activity").hidden = true;
  $("#log-state").textContent = activity
    ? `${activity.status} · ${formatTime(activity.elapsed)}`
    : "No active run";
  const consoleView = $("#console");
  const follow =
    consoleView.scrollHeight -
      consoleView.scrollTop -
      consoleView.clientHeight <
    40;
  const nextActivity = run
    ? `${run.id}/${activity.id || activity.started}`
    : "";
  const changed = nextActivity !== observedActivity;
  observedActivity = nextActivity;
  const logText =
    run?.logs?.join("\n") || "Logs will appear here when a stage starts.";
  if (consoleView.textContent !== logText) consoleView.textContent = logText;
  if (changed || follow) consoleView.scrollTop = consoleView.scrollHeight;
  if (!activity) {
    $("#activity-downloads").innerHTML = "";
    $("#activity-downloads").dataset.key = "";
    return;
  }
  if (changed && activity.status === "running") $("#logs").open = true;
  const phase = activityMessage(activity.phase) || "Waiting for stage output";
  const latest = activityMessage(activity.last_message);
  const warning = activityMessage(activity.last_warning);
  const currentStage = activity.current_stage || activity.stage;
  if (activity.status === "running" && currentStage === activeTab) {
    $("#live-activity").hidden = false;
    $("#live-activity").textContent =
      `Current step: ${phase}${warning ? " · Latest warning: " + warning : ""}`;
  }
  const stageRows = (activity.stages || [])
    .map((stage) => {
      const info = run.stages?.[stage] || {};
      const models = Object.entries(info.models || {})
        .map(
          ([role, model]) =>
            `${role}: ${serviceName(model.provider)} · ${model.model}`,
        )
        .join(" / ");
      const options = info.generation_options;
      const detail = [
        stage === "policy" ? "Saved extraction · no model call" : models,
        options
          ? `${scopeLabel(options.scenario_scope)} / ${profileLabel(options.scenario_profile)} / ${options.generation_mode} / per-pattern limit ${options.max_scenarios_per_pattern}`
          : "",
        stage !== "policy" && info.timeout
          ? info.timeout_scope === "evaluation"
            ? `${info.timeout}s deadline for the complete target + judge evaluation`
            : `${info.timeout}s timeout per model request`
          : "",
        displayMessage(info.error),
      ]
        .filter(Boolean)
        .map(escapeHTML)
        .join("<br>");
      return `<li><div><strong>${escapeHTML(names[stage])}</strong><span>${escapeHTML(info.status || "pending")}${info.started ? " · " + formatTime((info.ended || Date.now() / 1000) - info.started) : ""}</span></div><p>${detail}</p></li>`;
    })
    .join("");
  $("#activity-details").innerHTML = `
    <div class="activity-heading"><strong>${escapeHTML(activity.stage === "all" ? "Full demo" : names[activity.stage] || "Saved activity")}</strong><span>Started ${escapeHTML(new Date(activity.started * 1000).toLocaleTimeString())} · ${formatTime(activity.elapsed)} elapsed</span></div>
    <ul class="activity-stages">${stageRows}</ul>
    <div class="activity-progress"><strong>${activity.status === "running" ? "Current step" : "Last pipeline step"}</strong><p>${escapeHTML(phase)}</p>
    ${latest ? `<strong>Latest output${activity.last_output_at ? " · " + escapeHTML(new Date(activity.last_output_at * 1000).toLocaleTimeString()) : ""}</strong><p>${escapeHTML(latest)}</p>` : ""}
    ${activity.quiet >= 15 ? `<p class="activity-note">Worker still running; no new output for ${formatTime(activity.quiet)}. A model request may still be in progress.</p>` : ""}
    ${warning ? `<div class="activity-warning"><strong>Latest warning${activity.warning_count ? " · " + activity.warning_count + " warnings/errors recorded" : ""}</strong><p>${escapeHTML(warning)}</p></div>` : ""}
    ${activity.error ? `<div class="activity-warning"><strong>Execution error</strong><p>${escapeHTML(displayMessage(activity.error))}</p></div>` : ""}</div>`;
  const history = (run.activity_history || []).slice().reverse();
  const links = `<span>Showing the latest 160 log lines.</span>${download(activity.log_file, "Full execution log ↗")}${history.length ? `<details><summary>Earlier activity (${history.length})</summary>${history.map((item) => download(item.log_file, `${names[item.stage] || (item.stage === "all" ? "Full demo" : "Earlier activity")} · ${item.started ? new Date(item.started * 1000).toLocaleString() : "legacy log"} · ${item.status || "saved"}`)).join("")}</details>` : ""}`;
  // Keep an expanded history list open across polling updates.
  if ($("#activity-downloads").dataset.key !== nextActivity + history.length) {
    $("#activity-downloads").innerHTML = links;
    $("#activity-downloads").dataset.key = nextActivity + history.length;
  }
}

function renderPolicy(data) {
  return `<div class="report-toolbar"><div><span class="badge saved">Saved extraction</span><span>${data.count} matched entries · no live policy calls</span></div><div>${download(data.extraction, "Extraction JSON")}${download(data.report, "Open full report ↗")}</div></div><iframe class="policy-report" title="Interactive FS-ISAC policy report from PR 79" src="${escapeHTML(fileURL(data.report))}" sandbox="allow-scripts allow-downloads allow-popups allow-popups-to-escape-sandbox"></iframe>`;
}
function distribution(rows, key) {
  const result = {};
  for (const row of rows) {
    const label = row[key] || "Unspecified";
    result[label] = (result[label] || 0) + 1;
  }
  return Object.entries(result).sort((a, b) => b[1] - a[1]);
}
function chart(title, entries, interactive = false) {
  const max = Math.max(1, ...entries.map((e) => e[1]));
  return `<div class="chart"><h3>${escapeHTML(title)}</h3>${entries.map(([label, count]) => `<button class="bar-button" ${interactive ? `data-surface="${escapeHTML(label)}" aria-pressed="${surfaceFilter === label}"` : 'tabindex="-1"'}><span>${escapeHTML(label)}</span><b style="width:${(count / max) * 100}%"></b><strong>${count}</strong></button>`).join("") || "<small>No results yet</small>"}</div>`;
}
function renderScenarios(data) {
  const rows = data.scenarios || [];
  if (isSavedDemo()) selectedScenario = snapshot.run.results.artifact?.scenario_file || "";
  if (!rows.some((s) => s.file === selectedScenario))
    selectedScenario =
      rows.find((s) => !s.skip_reason)?.file || rows[0]?.file || "";
  return `<div class="results-inner"><div class="metrics">${metric(data.admitted ?? rows.length, "Admitted scenarios", true)}${metric(data.quarantined || 0, "Rejected scenarios")}${metric(rows.filter((s) => !s.skip_reason).length, "Scenarios writable in Garak", true)}</div><div class="charts">${chart("Injection surfaces · select to filter", distribution(rows, "surface"), true)}${chart(
    "Policy risk traceability",
    [
      ["Linked to a risk", rows.filter((s) => s.risk_id).length],
      ["No risk ID exported", rows.filter((s) => !s.risk_id).length],
    ],
  )}</div><div class="filter-row"><input id="scenario-search" type="search" placeholder="Search scenarios or risk IDs" aria-label="Search scenarios" value="${escapeHTML(scenarioSearch)}"><select id="surface-filter" aria-label="Filter by injection surface"><option value="">All injection surfaces</option>${distribution(
    rows,
    "surface",
  )
    .map(
      ([s]) =>
        `<option ${s === surfaceFilter ? "selected" : ""} value="${escapeHTML(s)}">${escapeHTML(s)}</option>`,
    )
    .join(
      "",
    )}</select><small id="scenario-count"></small></div><div id="scenario-list"></div><div class="report-toolbar"><span>${isSavedDemo() ? "The marked scenario is the source of the saved artifact." : "Select a scenario, then open Artifact Generator."}</span><div>${download(data.report, "Full scenario report ↗")}${download(data.run_dir + "/finalization-inventory.json", "Admission inventory")}</div></div><details class="technical"><summary>Technical details & rejection evidence</summary>${code({ inventory: data.inventory, rejected_scenarios: data.quarantine })}</details></div>`;
}
function fillScenarioList() {
  const data = snapshot?.run?.results?.scenarios;
  if (!data || !$("#scenario-list")) return;
  const filtered = (data.scenarios || []).filter(
    (s) =>
      (!surfaceFilter || s.surface === surfaceFilter) &&
      JSON.stringify([s.title, s.summary, s.id, s.risk_id])
        .toLowerCase()
        .includes(scenarioSearch.toLowerCase()),
  );
  $("#scenario-count").textContent = `${filtered.length} shown`;
  $("#scenario-list").innerHTML =
    filtered
      .map((s) => {
        const risk = snapshot.run.results.policy?.risks?.find(
          (r) => r.risk_id === s.risk_id,
        );
        const quote = risk?.evidence?.[0]?.text;
        return `<article class="scenario-card ${s.file === selectedScenario ? "selected" : ""}"><div class="scenario-top"><label><input type="radio" name="scenario" value="${escapeHTML(s.file)}" ${s.file === selectedScenario ? "checked" : ""} ${s.skip_reason || isSavedDemo() ? "disabled" : ""}><div><span class="id">${escapeHTML(s.id)}</span><h3>${escapeHTML(s.title)}</h3></div></label><span class="badge">${escapeHTML(s.surface)}</span></div><details ${s.file === selectedScenario ? "open" : ""}><summary>Scenario, policy evidence & behavior</summary><div class="scenario-body"><p>${escapeHTML(s.summary)}</p><div class="trace"><small>POLICY TRACE · ${escapeHTML(s.risk_id || "No risk ID exported")}</small>${escapeHTML(quote || risk?.risk_name || "See the scenario source for its risk mapping.")}</div>${s.skip_reason ? `<p>${escapeHTML(s.skip_reason)}</p>` : ""}<h4>Behavior specification</h4>${code(s.gherkin || "No separate behavior specification exported.")}<details class="technical"><summary>Scenario source</summary>${code(s.data)}</details><p style="margin-top:14px">${download(s.file, "Download scenario YAML")}</p></div></details></article>`;
      })
      .join("") ||
    empty(
      "No matching scenarios",
      "Clear the search or choose another injection surface.",
    );
  document.querySelectorAll('input[name="scenario"]').forEach((el) =>
    el.addEventListener("change", () => {
      selectedScenario = el.value;
      fillScenarioList();
    }),
  );
}
function renderArtifact(data) {
  const artifact = data.artifact || {},
    validation = data.validation || {},
    turns = artifact.turns || [];
  const rubrics = artifact.detector_rubric?.rubrics || {};
  return `<div class="results-inner"><div class="metrics">${metric(data.coverage || "—", "Garak platform coverage")}${metric(validation.ok === true ? "Passed" : "Failed", "Artifact validation", validation.ok === true)}${metric(turns.length, "Transcript turns")}</div><div class="trace"><small>SCENARIO → ARTIFACT</small>${escapeHTML(data.scenario_id)} · ${escapeHTML(data.coverage_reason || "")}<br><small>Validation checks the generated artifact. ${isSavedDemo() ? "Open Garak Evaluation to see the recorded target response." : "Open Garak Evaluation to test the target model."}</small></div><div class="conversation">${turns.map((t, i) => `<article class="turn ${t.adversarial ? "attack" : ""}"><header><span>${String(i + 1).padStart(2, "0")} / ${escapeHTML(t.role)}${t.name ? " · " + escapeHTML(t.name) : ""}</span>${t.adversarial ? '<span class="badge">Adversarial turn</span>' : ""}</header><pre>${escapeHTML(t.content || "")}</pre>${t.tool_calls ? code(t.tool_calls) : ""}</article>`).join("") || empty("No validated artifact written", "Inspect the validation evidence below. The original scenario is still available.")}</div><div class="rubrics"><div><h3>Attack success criteria</h3><ul>${(rubrics.attack_success || []).map((r) => `<li>${escapeHTML(r)}</li>`).join("")}</ul></div><div><h3>Attack blocked criteria</h3><ul>${(rubrics.attack_blocked || []).map((r) => `<li>${escapeHTML(r)}</li>`).join("")}</ul></div><details class="technical"><summary>Validation evidence & detector prompt</summary>${code(validation)}${code(artifact.detector_rubric?.judge_prompt || "")}</details><div class="report-toolbar"><span class="badge ${validation.ok ? "pass" : "fail"}">${validation.ok ? "Validated artifact" : "Validation failed"}</span><div>${download(data.file, "Garak artifact JSON")}${download(data.validation_file, "Validation JSON")}</div></div></div>`;
}
function renderEvaluation(data) {
  const labels = {
    attack_succeeded: "Attack succeeded",
    attack_not_demonstrated: "Attack not demonstrated",
    inconclusive: "Inconclusive",
  };
  const attempts = data.attempts || [];
  const confidence = attempts[0]?.confidence;
  return `<div class="results-inner"><div class="evaluation-verdict ${data.outcome === "attack_succeeded" ? "hit" : ""}"><span class="badge">${isSavedDemo() ? "Saved model test" : "Live model test"}</span><h3>${escapeHTML(labels[data.outcome] || "Evaluation result")}</h3><p>${escapeHTML(data.target_model)} · ${escapeHTML(serviceName(data.target_provider || "ollama"))} · ${attempts.length} response${attempts.length === 1 ? "" : "s"} evaluated</p></div><div class="metrics">${metric(confidence == null ? "—" : confidence + "/100", "Judge confidence in attack success")}${metric(data.threshold || 70, "Success cutoff")}${metric(data.judge_model || "—", "Judge model")}</div><div class="trace"><small>ARTIFACT → TARGET → JUDGE</small>${escapeHTML(data.scenario_id)}<br><small>Real model response to the artifact’s replayed context. Proposed tool calls are captured; external tools are not executed. One scenario does not establish overall model safety.</small></div>${attempts.map((a, i) => `<article class="turn"><header><span>${i + 1} / ${escapeHTML(data.target_model)} response</span><span class="badge">${escapeHTML(labels[a.outcome])}</span></header><pre>${escapeHTML(a.response || "The model responded with tool calls.")}</pre>${a.tool_calls?.length ? "<h4>Proposed tool calls</h4>" + code(a.tool_calls) : ""}</article><div class="judge-reason"><h3>Why Garak reached this result</h3><p>${escapeHTML(a.reasoning)}</p></div>`).join("")}<div class="report-toolbar"><span>Garak PR #11 · InjectionJudge</span><div>${download(data.report_file, "Garak report JSONL")}${download(data.conversation_file, "Replayed conversation")}${download(data.artifact_file, "Source artifact")}</div></div><details class="technical"><summary>Execution details</summary>${code({ target: data.target_base_url, model: data.target_model, judge: data.judge_model, probe: "injection.IndirectInjection", detector: "injection_judge.InjectionJudge", revision: data.garak_revision, tool_execution: false })}</details></div>`;
}
function render() {
  controls();
  renderActivity();
  const run = snapshot?.run,
    info = run?.stages?.[activeTab],
    data = run?.results?.[activeTab];
  const key = JSON.stringify([selectedRun, activeTab, info?.status, data]);
  if (key === renderKey) return;
  renderKey = key;
  if (
    canRenderResult(activeTab, data) &&
    (info?.status === "completed" || info?.status === "failed")
  ) {
    const renderer = {
      policy: renderPolicy,
      scenarios: renderScenarios,
      artifact: renderArtifact,
      evaluation: renderEvaluation,
    }[activeTab];
    $("#results").innerHTML =
      (data.status === "failed"
        ? `<div class="notice">${escapeHTML(displayMessage(data.error))}</div>`
        : "") + renderer(data);
    if (activeTab === "scenarios") {
      fillScenarioList();
      $("#scenario-search").addEventListener("input", (e) => {
        scenarioSearch = e.target.value;
        fillScenarioList();
      });
      $("#surface-filter").addEventListener("change", (e) => {
        surfaceFilter = e.target.value;
        fillScenarioList();
      });
      document.querySelectorAll("[data-surface]").forEach((el) =>
        el.addEventListener("click", () => {
          surfaceFilter =
            surfaceFilter === el.dataset.surface ? "" : el.dataset.surface;
          renderKey = "";
          render();
        }),
      );
    }
  } else if (info?.status === "running") {
    $("#results").innerHTML = empty(
      `${names[activeTab]} is running`,
      activeTab === "policy"
        ? "Building the interactive report from saved extraction data."
        : "The model is working. Real activity appears below; results will appear when the stage completes.",
      "◌",
    );
  } else if (["failed", "cancelled", "interrupted"].includes(info?.status)) {
    $("#results").innerHTML = empty(
      `${names[activeTab]} ${info.status}`,
      displayMessage(info.error) || "You can run this stage again.",
    );
  } else {
    $("#results").innerHTML = empty(
      {
        policy: "Start with policy evidence",
        scenarios: "Generate scenarios grounded in this policy",
        artifact: "Turn a scenario into a test artifact",
        evaluation: "Test the artifact against a real model",
      }[activeTab],
      {
        policy:
          "Load the saved FS-ISAC extraction to explore the interactive policy report. No policy model calls are needed.",
        scenarios:
          "Load the policy results, choose generation options above, then run scenarios. Admitted scenarios and their evidence will appear here.",
        artifact:
          "Generate scenarios, choose one, then build its Garak transcript and detector rubric.",
        evaluation:
          "Generate a validated artifact, then replay it against " +
          (snapshot?.settings?.target_model || "Qwen") +
          " via " +
          serviceName(snapshot?.settings?.target_provider || "ollama") +
          ". Garak evaluates the real reply and proposed tool calls using the artifact’s rubric.",
      }[activeTab],
    );
  }
}

async function poll() {
  try {
    const data = await api(
      "/api/state" +
        (selectedRun ? "?run=" + encodeURIComponent(selectedRun) : ""),
    );
    if (pinnedRun && (!data.run?.read_only || data.run.id !== pinnedRun))
      throw new Error("This link does not identify a saved demo snapshot.");
    snapshot = data;
    const nextRun = chooseRunId(selectedRun, data, observedActiveId, pinnedRun);
    observedActiveId = data.active_id;
    if (nextRun && nextRun !== selectedRun) {
      selectedRun = nextRun;
      selectedScenario = "";
      return await poll();
    }
    const scenarioModel = isSavedDemo()
      ? data.run.stages.scenarios.models?.scenario || {provider: "", model: data.run.model || "Not recorded"}
      : resolveModel(data.settings, "scenario");
    $("#model-label").textContent =
      `${serviceName(scenarioModel.provider)} · ${scenarioModel.model || "Choose model"}`;
    const historyHTML =
      (data.history.length
        ? ""
        : '<option value="">No saved runs yet</option>') +
      (isSavedDemo() ? [data.run] : data.history)
        .map(
          (r) =>
            `<option value="${escapeHTML(r.id)}">${escapeHTML(r.id)} · ${r.read_only ? "Saved demo" : escapeHTML(r.status)}</option>`,
        )
        .join("");
    if ($("#history").innerHTML !== historyHTML)
      $("#history").innerHTML = historyHTML;
    $("#history").value = selectedRun;
    render();
  } catch (error) {
    notice((staticDemo ? "Cannot load the published demo. " : "Cannot reach the local demo server. ") + error.message);
    controls();
  }
}
$("#scenario-scope").addEventListener("change", async () => {
  const scope = $("#scenario-scope").value;
  if (scope === "full") { scenarioOptionsDirty = true; renderScenarioOptions(snapshot?.busy); return; }
  pending = true;
  notice("");
  controls();
  try {
    snapshot.settings = await api("/api/settings", snapshot.scenario_presets[scope]);
    scenarioOptionsDirty = false;
    await poll();

  } catch (error) {
    notice(error.message);
  } finally {
    pending = false;
    controls();
  }
});
async function start(stage) {
  if (stage === "scenarios" || stage === "all") {
    if (!$("#scenario-options").checkValidity()) {
      selectTab("scenarios");
      $("#scenario-options").reportValidity();
      return;
    }
  }
  pending = true;
  notice("");
  controls();
  try {
    if (stage === "scenarios" || stage === "all") {
      const settings = await api("/api/settings", readScenarioOptions());
      snapshot.settings = settings;
      scenarioOptionsDirty = false;
    }
    const result = await api("/api/start", {
      stage,
      run: selectedRun || null,
      scenario: stage === "artifact" ? selectedScenario : "",
    });
    selectedRun = result.run_id;
    renderKey = "";
    selectTab(stage === "all" ? "scenarios" : stage);
    if (stage !== "policy") $("#logs").open = true;
    await poll();
  } catch (error) {
    notice(error.message);
  } finally {
    pending = false;
    controls();
  }
}

$("#scenario-options").addEventListener("submit", (event) => {
  event.preventDefault();
});
$("#scenario-options").addEventListener("input", () => {
  scenarioOptionsDirty = true;
  renderScenarioOptions(snapshot?.busy || pending);
});
document
  .querySelectorAll("[data-tab]")
  .forEach((el) =>
    el.addEventListener("click", () => selectTab(el.dataset.tab)),
  );
$("#run-all").addEventListener("click", () => start("all"));
$("#run-stage").addEventListener("click", () => start(activeTab));
$("#cancel").addEventListener("click", async () => {
  try {
    await api("/api/cancel", { run: snapshot?.active_id });
    await poll();
  } catch (e) {
    notice(e.message);
  }
});
$("#history").addEventListener("change", async (e) => {
  if (snapshot?.history.find(run => run.id === e.target.value)?.read_only) {
    window.location.assign("/?saved=" + encodeURIComponent(e.target.value));
    return;
  }
  selectedRun = e.target.value;
  selectedScenario = "";
  renderKey = "";
  await poll();
});
$("#recording").addEventListener("click", () => {
  const active = document.body.classList.toggle("recording");
  $("#recording").setAttribute("aria-pressed", active);
  $("#recording").textContent = active
    ? "Exit recording view"
    : "Recording view";
});
function setTheme(dark) {
  document.documentElement.classList.toggle("pf-v6-theme-dark", dark);
  $("#theme").textContent = dark ? "Light mode" : "Dark mode";
  localStorage.setItem("asago-demo-dark", String(dark));
}
setTheme(localStorage.getItem("asago-demo-dark") !== "false");
$("#theme").addEventListener("click", () =>
  setTheme(!document.documentElement.classList.contains("pf-v6-theme-dark")),
);
const modelRoles = {
  scenario: "Scenario generation",
  artifact: "Artifact generation",
  target: "Garak target",
  judge: "Garak judge",
};
let modelDraft = {},
  modelLists = {},
  modelManual = {},
  discoveryVersion = 0;
function serviceName(provider) {
  return (
    { ollama: "Ollama", litellm: "LiteLLM", google: "Google Gemini" }[
      provider
    ] || provider
  );
}
function modelKey(role) {
  return role === "scenario" ? "model" : `${role}_model`;
}
function discoverySignature(provider) {
  if (provider === "google") return $("#google-api-key").value;
  return provider === "litellm"
    ? `${$("#base-url").value.trim()}|${$("#api-key").value}`
    : $("#ollama-base-url").value.trim();
}
function renderModelChoices() {
  for (const role of Object.keys(modelRoles)) {
    const provider = resolveModel(modelDraft, role).provider;
    const inherited = modelDraft[`${role}_provider`] === "same";
    const current = modelDraft[modelKey(role)] || "";
    const select = $(`#${role}-model-choice`);
    const catalog = modelLists[provider];
    const models =
      catalog?.signature === discoverySignature(provider) ? catalog.models : [];
    const choices = [
      ...new Set([
        ...models,
        ...(!modelManual[role] && current ? [current] : []),
      ]),
    ];
    select.innerHTML =
      `<option value="">${inherited ? "Same model as " + (role === "judge" ? "artifact generation" : "scenario generation") : "Choose a model…"}</option>` +
      choices
        .map(
          (model) =>
            `<option value="${escapeHTML(model)}">${escapeHTML(model)}</option>`,
        )
        .join("") +
      '<option value="__manual__">Enter a model name…</option>';
    select.value = modelManual[role] ? "__manual__" : current;
    select.required = !inherited;
    const custom = $(`#${role}-model-custom`);
    custom.hidden = !modelManual[role];
    custom.required = !!modelManual[role];
    if (document.activeElement !== custom) custom.value = current;
    const resolved = resolveModel(modelDraft, role);
    $(`#${role}-model-resolved`).textContent = resolved.model
      ? `${serviceName(resolved.provider)} · ${resolved.model}`
      : `Choose a ${serviceName(resolved.provider)} model.`;
  }
}
async function loadProviderModels(provider) {
  const button = $(`#${provider}-models-load`),
    status = $(`#${provider}-models-status`);
  if (
    provider === "google" &&
    !$("#google-api-key").value.trim() &&
    !snapshot.settings.google_api_key_configured
  ) {
    status.textContent = "Enter your Google API key below, then load models.";
    return;
  }
  const version = discoveryVersion,
    signature = discoverySignature(provider);
  button.disabled = true;
  status.textContent = "Loading models…";
  try {
    const result = await api("/api/models", {
      provider,
      ...(provider === "google"
        ? { api_key: $("#google-api-key").value }
        : {
            base_url: $(
              provider === "litellm" ? "#base-url" : "#ollama-base-url",
            ).value.trim(),
          }),
      ...(provider === "litellm" ? { api_key: $("#api-key").value } : {}),
    });
    if (
      version !== discoveryVersion ||
      signature !== discoverySignature(provider)
    )
      return;
    modelLists[provider] = { signature, models: result.models };
    status.textContent = result.models.length
      ? `${result.models.length} models available.`
      : "No models returned. Install or configure a model, then reload.";
    renderModelChoices();
  } catch (error) {
    if (
      version !== discoveryVersion ||
      signature !== discoverySignature(provider)
    )
      return;
    status.textContent = `Could not load models: ${error.message} You can enter a model name manually.`;
  } finally {
    if (version === discoveryVersion) button.disabled = false;
  }
}
$("#settings-open").addEventListener("click", () => {
  const s = snapshot.settings;
  discoveryVersion++;
  modelDraft = { ...s };
  modelLists = {};
  modelManual = {};
  $("#base-url").value = s.base_url || "";
  $("#api-key").value = "";
  $("#google-api-key").value = "";
  $("#ollama-base-url").value =
    s.ollama_base_url || s.target_base_url || "http://127.0.0.1:11434/v1";
  $("#key-state").textContent = s.api_key_configured
    ? "A key is configured locally."
    : "No API key configured.";
  $("#google-key-state").textContent = s.google_api_key_configured
    ? "A Google key is configured locally."
    : "No Google key configured.";
  $("#connection-state").textContent = "";
  $("#model-roles").innerHTML = Object.entries(modelRoles)
    .map(
      ([role, label]) =>
        `<div class="model-role"><h3>${label}</h3><div><label for="${role}-provider">${label} service</label><select id="${role}-provider">${["artifact", "judge"].includes(role) ? `<option value="same">Same service as ${role === "judge" ? "artifact" : "scenario"}</option>` : ""}<option value="litellm">LiteLLM</option><option value="ollama">Ollama</option><option value="google">Google Gemini</option></select></div><div><label for="${role}-model-choice">${label} model</label><select id="${role}-model-choice"></select><input id="${role}-model-custom" aria-label="${label} custom model" placeholder="Exact served model name" hidden /><small id="${role}-model-resolved"></small></div></div>`,
    )
    .join("");
  for (const role of Object.keys(modelRoles)) {
    const provider = $(`#${role}-provider`);
    provider.value =
      s[`${role}_provider`] ||
      { scenario: "litellm", target: "ollama" }[role] ||
      "same";
    modelDraft[`${role}_provider`] = provider.value;
    provider.addEventListener("change", () => {
      modelDraft[`${role}_provider`] = provider.value;
      modelDraft[modelKey(role)] = "";
      modelManual[role] = false;
      renderModelChoices();
      const service = resolveModel(modelDraft, role).provider;
      if (modelLists[service]?.signature !== discoverySignature(service))
        loadProviderModels(service);
    });
    $(`#${role}-model-choice`).addEventListener("change", (event) => {
      modelManual[role] = event.target.value === "__manual__";
      modelDraft[modelKey(role)] = modelManual[role] ? "" : event.target.value;
      renderModelChoices();
      if (modelManual[role]) $(`#${role}-model-custom`).focus();
    });
    $(`#${role}-model-custom`).addEventListener("input", (event) => {
      modelDraft[modelKey(role)] = event.target.value;
      renderModelChoices();
    });
  }
  renderModelChoices();
  $("#settings-dialog").showModal();
  for (const provider of ["litellm", "ollama", "google"]) {
    $(`#${provider}-models-load`).disabled = false;
    if (
      provider === "google" ||
      $(provider === "litellm" ? "#base-url" : "#ollama-base-url").value
    )
      loadProviderModels(provider);
    else
      $(`#${provider}-models-status`).textContent =
        "Enter the service URL to load models.";
  }
});
$("#settings-close").addEventListener("click", () =>
  $("#settings-dialog").close(),
);
$("#settings-dialog").addEventListener("close", () => {
  discoveryVersion++;
});
for (const provider of ["litellm", "ollama", "google"]) {
  $(`#${provider}-models-load`).addEventListener("click", () =>
    loadProviderModels(provider),
  );
}
for (const selector of [
  "#base-url",
  "#ollama-base-url",
  "#api-key",
  "#google-api-key",
]) {
  $(selector).addEventListener("input", () => {
    const provider =
      selector === "#google-api-key"
        ? "google"
        : selector === "#ollama-base-url"
          ? "ollama"
          : "litellm";
    $(`#${provider}-models-status`).textContent =
      "Connection changed. Reload models to refresh the list.";
    renderModelChoices();
  });
}
$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#models-save").disabled = true;
  try {
    const choices = Object.fromEntries(
      Object.keys(modelRoles).flatMap((role) => [
        [`${role}_provider`, modelDraft[`${role}_provider`]],
        [modelKey(role), (modelDraft[modelKey(role)] || "").trim()],
      ]),
    );
    await api("/api/settings", {
      ...choices,
      base_url: $("#base-url").value.trim(),
      ollama_base_url: $("#ollama-base-url").value.trim(),
      api_key: $("#api-key").value,
      google_api_key: $("#google-api-key").value,
    });
    $("#settings-dialog").close();
    await poll();
  } catch (error) {
    $("#connection-state").textContent = error.message;
  } finally {
    $("#models-save").disabled = false;
  }
});
async function tick() {
  await poll();
  if (!staticDemo) setTimeout(tick, 1500);
}
tick();
