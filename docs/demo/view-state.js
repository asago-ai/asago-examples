(function (root) {
  function chooseRunId(selected, state, previousActive, pinned = "") {
    if (pinned) return pinned;
    if (state.run?.read_only && selected === state.run.id) return selected;
    if (state.active_id && state.active_id !== previousActive)
      return state.active_id;
    return selected || state.active_id || state.history?.[0]?.id || "";
  }
  function canRenderResult(stage, result) {
    if (!result) return false;
    if (stage === "policy")
      return typeof result.report === "string" && !!result.report;
    if (stage === "scenarios") return Array.isArray(result.scenarios);
    if (stage === "artifact")
      return !!result.artifact && typeof result.artifact === "object";
    if (stage === "evaluation") return Array.isArray(result.attempts);
    return false;
  }
  function resolveModel(config, role) {
    const defaults = {
      scenario: "litellm",
      artifact: "same",
      target: "ollama",
      judge: "same",
    };
    const provider = config[`${role}_provider`] || defaults[role];
    const model = config[role === "scenario" ? "model" : `${role}_model`] || "";
    if (provider === "same" && ["artifact", "judge"].includes(role)) {
      const parent = resolveModel(
        config,
        role === "artifact" ? "scenario" : "artifact",
      );
      return { provider: parent.provider, model: model || parent.model };
    }
    return { provider, model };
  }
  async function readAPIResponse(response) {
    if (
      !(response.headers.get("content-type") || "").includes("application/json")
    ) {
      throw new Error(
        `The local demo returned a non-JSON response (HTTP ${response.status}). Its port may belong to another app. Restart Asago on a free port and open the new URL.`,
      );
    }
    return response.json();
  }
  function activityView(run, now = Date.now() / 1000) {
    if (!run) return null;
    const latest = Object.entries(run.stages || {})
      .filter(([, info]) => info.started)
      .sort((a, b) => b[1].started - a[1].started)[0];
    const logs = run.logs || [];
    const recent = [...logs].reverse();
    const activity = run.activity || {
      stage: latest?.[0],
      stages: latest ? [latest[0]] : [],
      started: latest?.[1].started || run.started,
      ended: latest?.[1].ended,
      status: run.status,
      phase: recent.find((line) => /\[Stage [^\]]+\]/.test(line)),
      last_message: logs.at(-1),
      last_warning: recent.find((line) => /WARNING|ERROR|timed out/.test(line)),
      error: latest?.[1].error || run.error,
      log_file: "console.log",
    };
    return {
      ...activity,
      elapsed: Math.max(0, (activity.ended || now) - activity.started),
      quiet:
        activity.status === "running" && activity.last_output_at
          ? Math.max(0, now - activity.last_output_at)
          : null,
    };
  }
  function renderSearchTree(plan) {
    const escape = value => String(value).replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
    const count = (n, label) => `${n} ${label}${n === 1 ? "" : "s"}`;
    const inputBranch = input => `
      <li><div class="tree-input">
        <strong>${escape(input.name)}</strong>
        <span>${escape(input.controllability)} · ${count(input.candidate_count, "candidate")} · ${input.after_rules} after rules</span>
        <small>${input.techniques.map(escape).join(" · ")}</small>
      </div></li>`;
    const seedBranch = seed => `
      <li><details>
        <summary><strong>${escape(seed.id)}</strong> ${escape(seed.name)}</summary>
        ${seed.inputs.length
          ? `<ul>${seed.inputs.map(inputBranch).join("")}</ul>`
          : '<p class="tree-skipped">Not expanded: no applicable technique or required capability.</p>'}
      </details></li>`;
    const threatBranch = threat => `
      <li><details open>
        <summary><strong>${escape(threat.id)}</strong> ${escape(threat.name)}
          <span>${count(threat.seeds.length, "seed")}</span>
        </summary>
        <ul>${threat.seeds.map(seedBranch).join("")}</ul>
      </details></li>`;
    return `<div class="tree-root">${escape(plan.policy)} → ${escape(plan.profile)}</div>
      <ul>${plan.threats.map(threatBranch).join("")}</ul>`;
  }
  const exports = {
    renderSearchTree,
    chooseRunId,
    canRenderResult,
    resolveModel,
    readAPIResponse,
    activityView,
  };
  if (typeof module !== "undefined") module.exports = exports;
  else root.AsagoViewState = exports;
})(typeof window === "undefined" ? {} : window);
