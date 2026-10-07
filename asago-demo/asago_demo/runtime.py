"""Configuration and serialized, cancellable execution for the local demo."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("policy", "scenarios", "artifact", "evaluation")
SECRET_FIELDS = {"api_key", "google_api_key"}
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
SCENARIO_DEFAULTS = {
    "scenario_scope": "full",
    "scenario_profile": "direct",
    "generation_mode": "coverage",
    "max_scenarios_per_pattern": 1,
}
DEMO_PRESET = {
    "scenario_scope": "recording",
    "scenario_profile": "direct",
    "generation_mode": "exhaustive",
    "max_scenarios_per_pattern": 1,
}
SCENARIO_PRESETS = {
    "recording": DEMO_PRESET,
    "indirect": {
        **DEMO_PRESET,
        "scenario_scope": "indirect",
        "scenario_profile": "indirect",
        "max_scenarios_per_pattern": 3,
    },
}
FULL_SEARCH_OPTIONS = {
    "scenario_scope": "full",
    "scenario_profile": "full",
    "generation_mode": "exhaustive",
    "max_scenarios_per_pattern": 1,
}
SCENARIO_PROFILES = {
    "indirect": "klarna-indirect-demo-profile.yaml",
    "direct": "klarna-direct-canary-profile.yaml",
    "full": "klarna-capability-profile.yaml",
}
MODEL_DEFAULTS = {
    "scenario_provider": "litellm",
    "artifact_provider": "same",
    "target_provider": "ollama",
    "judge_provider": "same",
    "judge_model": "",
}


def provider_connection(config: dict, provider: str) -> dict:
    if provider == "litellm":
        url = config.get("base_url", "")
        key = config.get("api_key") or "none"
    elif provider == "ollama":
        url = (
            config.get("ollama_base_url")
            or config.get("target_base_url")
            or "http://127.0.0.1:11434/v1"
        )
        if not urlparse(url).path.strip("/"):
            url = url.rstrip("/") + "/v1"
        key = "ollama"
    elif provider == "google":
        url = GOOGLE_BASE_URL
        key = config.get("google_api_key", "")
        if not key:
            raise ValueError("Add your Google Gemini API key in Models & connections")
    else:
        raise ValueError("Choose LiteLLM, Ollama or Google Gemini")
    return {"provider": provider, "base_url": url.rstrip("/"), "api_key": key}


def model_connection(config: dict, role: str) -> dict:
    if role not in {"scenario", "artifact", "target", "judge"}:
        raise ValueError("Unknown model role")
    provider = config.get(f"{role}_provider", MODEL_DEFAULTS[f"{role}_provider"])
    model_key = "model" if role == "scenario" else f"{role}_model"
    model = config.get(
        model_key, {"scenario": "gemma-4-26b", "target": "qwen2.5:14b"}.get(role, "")
    )
    if provider == "google":
        model = model.removeprefix("models/")
    if provider == "same" and role in {"artifact", "judge"}:
        parent = model_connection(config, "scenario" if role == "artifact" else "artifact")
        resolved_model = model or parent["model"]
        if parent["provider"] == "google":
            resolved_model = resolved_model.removeprefix("models/")
        return {**parent, "model": resolved_model}
    return {**provider_connection(config, provider), "model": model}


def scenario_options(config: dict) -> dict:
    options = {key: config.get(key, value) for key, value in SCENARIO_DEFAULTS.items()}
    if options["scenario_profile"] not in SCENARIO_PROFILES:
        raise ValueError("Choose a supported Klarna profile")
    if options["generation_mode"] not in ("coverage", "exhaustive"):
        raise ValueError("Choose coverage or exhaustive generation")
    cap = options["max_scenarios_per_pattern"]
    if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= 10:
        raise ValueError("Variants per attack pattern must be a whole number from 1 to 10")
    if options["scenario_scope"] not in {"full", "quick3", "recording", "indirect"}:
        raise ValueError("Choose a preset or full search")
    if options["scenario_scope"] != "full":
        options.update(generation_mode="exhaustive", max_scenarios_per_pattern=1)
    if options["scenario_scope"] == "recording":
        options["scenario_profile"] = "direct"
    if options["scenario_scope"] in SCENARIO_PRESETS:
        preset = SCENARIO_PRESETS[options["scenario_scope"]]
        options.update({key: preset[key] for key in SCENARIO_DEFAULTS})
    return options


def redact_value(value, config):
    if isinstance(value, dict):
        return {redact_value(k, config): redact_value(v, config) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, config) for v in value]
    if not isinstance(value, str):
        return value
    for field in SECRET_FIELDS:
        key = config.get(field, "")
        if key and key != "none":
            value = value.replace(key, "[redacted]")
    return re.sub(r"(?i)(Bearer\s+)[^\s\"'\\]+", r"\1[redacted]", value)


def redacted_file(path, config):
    text = path.read_text()
    if path.suffix == ".json":
        return json.dumps(redact_value(json.loads(text), config), indent=2)
    if path.suffix == ".jsonl":
        return "".join(
            json.dumps(redact_value(json.loads(line), config)) + "\n"
            for line in text.splitlines()
            if line.strip()
        )
    return redact_value(text, config)


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def safe_child(root: Path, name: str) -> Path:
    path = Path(name)
    if path.is_absolute():
        raise ValueError("Absolute paths are not allowed")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Path is outside the demo outputs")
    return resolved


class Settings:
    FIELDS = {
        "base_url",
        "model",
        "api_key",
        "google_api_key",
        "artifact_model",
        "timeout",
        "target_base_url",
        "target_model",
        *SCENARIO_DEFAULTS,
        *MODEL_DEFAULTS,
        "ollama_base_url",
    }

    def __init__(self, root: Path = ROOT, defaults: dict | None = None):
        self.path = root / "settings.json"
        if defaults is None:
            from dotenv import dotenv_values

            env = {
                **dotenv_values(root.parent / ".env"),
                **dotenv_values(root / ".env"),
                **os.environ,
            }
            defaults = {
                "base_url": env.get("ASAGO_SCENARIO_GENERATOR_MODEL_BASE_URL")
                or env.get("OPENAI_BASE_URL", ""),
                "api_key": env.get("ASAGO_SCENARIO_GENERATOR_API_KEY")
                or env.get("OPENAI_API_KEY", "none"),
                "google_api_key": env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY", ""),
                "model": env.get("ASAGO_SCENARIO_GENERATOR_MODEL_NAME", "gemma-4-26b"),
                "artifact_model": env.get("REDTEAM_MODEL", ""),
                "timeout": 300,
                "target_base_url": "http://127.0.0.1:11434/v1",
                "target_model": "qwen2.5:14b",
            }
        self.defaults = {**SCENARIO_DEFAULTS, **MODEL_DEFAULTS, **defaults}

    def private(self) -> dict:
        saved = json.loads(self.path.read_text()) if self.path.exists() else {}
        return {**self.defaults, **saved}

    def public(self) -> dict:
        data = self.private()
        return {
            **{k: v for k, v in data.items() if k not in SECRET_FIELDS},
            "api_key_configured": bool(data.get("api_key")),
            "google_api_key_configured": bool(data.get("google_api_key")),
        }

    def preview(self, changes: dict) -> dict:
        """Validate a draft without replacing saved settings or credentials."""
        if not isinstance(changes, dict) or set(changes) - self.FIELDS:
            raise ValueError("Unknown configuration field")
        values = self.private()
        for key, value in changes.items():
            if key == "timeout":
                if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= 900:
                    raise ValueError("Timeout must be between 10 and 900 seconds")
            elif key == "max_scenarios_per_pattern":
                scenario_options({**values, key: value})
            elif not isinstance(value, str) or len(value) > 4096:
                raise ValueError("Configuration fields must be text")
            if key in SECRET_FIELDS and not value:
                continue
            values[key] = value.strip() if isinstance(value, str) else value
        scenario_options(values)
        for role in ("scenario", "artifact", "target", "judge"):
            provider = values[f"{role}_provider"]
            allowed = (
                ("litellm", "ollama", "google", "same")
                if role in {"artifact", "judge"}
                else ("litellm", "ollama", "google")
            )
            if provider not in allowed:
                raise ValueError(f"Invalid service for {role}")
            if not model_connection(values, role)["model"].strip():
                raise ValueError(f"Choose a model for {role}")
        for field in ("base_url", "target_base_url", "ollama_base_url"):
            parsed = urlparse(values.get(field, ""))
            if values.get(field) and (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Enter an HTTP(S) API base URL without credentials")
        return values

    def update(self, changes: dict) -> None:
        values = self.preview(changes)
        connection_fields = {
            *MODEL_DEFAULTS,
            "model",
            "artifact_model",
            "target_model",
            "base_url",
            "ollama_base_url",
            "target_base_url",
        }
        if set(changes) & connection_fields:
            for role in ("scenario", "artifact", "target", "judge"):
                if not model_connection(values, role)["base_url"]:
                    raise ValueError(f"Enter the service URL for {role}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(values, handle, indent=2)


class Coordinator:
    def __init__(self, root: Path = ROOT, settings: Settings | None = None):
        self.root = root
        self.runs = root / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.settings = settings or Settings(root)
        self.lock = threading.RLock()
        self.thread = None
        self.process = None
        self.stop = threading.Event()
        self.active_id = None
        self.active_stage = None
        self.state = None
        # A server restart cannot make an interrupted run appear to be running.
        saved_states = sorted(self.runs.glob("*/state.json"), key=lambda p: p.stat().st_mtime)
        for path in saved_states:
            state = json.loads(path.read_text())
            if state.get("read_only"):
                continue
            self.active_id = path.parent.name
            if state.get("status") == "running":
                state["status"] = "interrupted"
                if state.get("activity"):
                    state["activity"].update(
                        status="interrupted",
                        ended=time.time(),
                        error="Server stopped during this execution",
                    )
                for stage in state["stages"].values():
                    if stage["status"] == "running":
                        stage.update(
                            status="interrupted", error="Server stopped during this stage"
                        )
                atomic_json(path, state)

    @property
    def busy(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def redact(self, value: str, config: dict | None = None) -> str:
        return redact_value(value, config or self.settings.private())

    def command(self, stage: str, run: Path) -> list[str]:
        python = self.root.parent / ".venv/bin/python"
        if stage == "evaluation":
            python = self.root / ".garak-venv/bin/python"
            if not python.exists():
                raise ValueError("Run ./asago-demo/setup.sh to install Garak PR #11")
        if not python.exists():
            python = Path(sys.executable)
        return [str(python), "-u", str(self.root / "asago_demo/worker.py"), stage, str(run)]

    def _save(self):
        atomic_json(self.runs / self.active_id / "state.json", self.state)

    def _begin_activity(self, stage: str, folder: Path):
        """One log per button/notebook execution; keep all stages of Run demo together."""
        archive = self.state.setdefault("activity_history", [])
        (folder / "activity").mkdir(exist_ok=True)
        if previous := self.state.get("activity"):
            archive.append(previous)
        elif (folder / "console.log").exists():
            # Preserve logs from demos recorded before execution history was added.
            legacy = f"activity/legacy-{uuid.uuid4().hex[:8]}.log"
            (folder / "console.log").replace(folder / legacy)
            archive.append({"stage": "legacy", "log_file": legacy})
        execution_id = uuid.uuid4().hex[:12]
        self.state["activity"] = {
            "id": execution_id,
            "stage": stage,
            "stages": list(STAGES) if stage == "all" else [stage],
            "started": time.time(),
            "status": "running",
            "log_file": f"activity/{execution_id}.log",
            "warning_count": 0,
        }
        self.state["logs"] = []
        self.state.pop("error", None)
        (folder / "console.log").write_text("")

    def _activity_log(self, message: str, config: dict, *, output=False):
        with self.lock:
            activity = self.state["activity"]
            clean = re.sub(r"\x1b\[[0-9;]*m", "", self.redact(message.rstrip(), config))
            now = time.time()
            stamp = datetime.fromtimestamp(now, UTC).strftime("%H:%M:%S UTC")
            line = f"[{stamp}] [{self.active_stage}] {clean}"
            if output and clean:
                activity.update(last_output_at=now, last_message=clean)
                if match := re.search(r"\[Stage [^\]]+\].*", clean):
                    activity["phase"] = match.group()
                if re.search(r"\b(WARNING|ERROR)\b|timed out|retrying", clean):
                    activity["warning_count"] += 1
                    activity["last_warning"] = clean
            folder = self.runs / self.active_id
            for name in ("console.log", activity["log_file"]):
                with (folder / name).open("a") as handle:
                    handle.write(line + "\n")
            self.state["logs"] = (self.state["logs"] + [line])[-160:]
            self._save()

    def current(self, run_id: str | None = None) -> dict | None:
        with self.lock:
            run_id = run_id or self.active_id
            if not run_id:
                return None
            folder = safe_child(self.runs, run_id)
            if not (folder / "state.json").is_file():
                raise ValueError("Run not found")
            state = json.loads((folder / "state.json").read_text())
            for stage in STAGES:
                state["stages"].setdefault(stage, {"status": "pending"})
            state["_path"] = str(folder)
            state["results"] = {}
            for stage in STAGES:
                path = folder / f"{stage}.json"
                if path.exists():
                    state["results"][stage] = json.loads(path.read_text())
            return redact_value(state, self.settings.private())

    def history(self) -> list[dict]:
        history = []
        for path in sorted(self.runs.glob("*/state.json"), reverse=True)[:40]:
            state = json.loads(path.read_text())
            history.append(
                {
                    k: state.get(k)
                    for k in ("id", "started", "status", "model", "read_only", "snapshot")
                }
            )
        return history

    def start(self, stage: str, run_id: str | None = None, scenario: str = "") -> str:
        if stage not in (*STAGES, "all"):
            raise ValueError("Unknown stage")
        with self.lock:
            selected_id = run_id or (self.active_id if stage not in {"policy", "all"} else None)
            if selected_id and self.current(selected_id).get("read_only"):
                raise ValueError(
                    "This saved demo is read-only. Return to the live workspace to start a run."
                )
            if self.busy:
                raise ValueError("A run is already running")
            config = self.settings.private()
            if stage in {"policy", "all"}:
                run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
                folder = self.runs / run_id
                folder.mkdir()
                self.state = {
                    "id": run_id,
                    "started": time.time(),
                    "status": "running",
                    "model": config.get("model", ""),
                    "logs": [],
                    "stages": {s: {"status": "pending"} for s in STAGES},
                }
            else:
                state = self.current(run_id)
                if not state or state["stages"]["policy"]["status"] != "completed":
                    raise ValueError("Run Policy Mapper first")
                if (
                    stage in {"artifact", "evaluation"}
                    and state["stages"]["scenarios"]["status"] != "completed"
                ):
                    raise ValueError("Run Scenario Generator first")
                if stage == "evaluation" and state["stages"]["artifact"]["status"] != "completed":
                    raise ValueError("Run Artifact Generator first")
                run_id = state["id"]
                folder = safe_child(self.runs, run_id)
                self.state = {k: v for k, v in state.items() if k not in {"_path", "results"}}
                self.state["status"] = "running"
                if scenario:
                    data = state["results"].get("scenarios", {})
                    if scenario not in {s["file"] for s in data.get("scenarios", [])}:
                        raise ValueError("Select a scenario from this run")
                    atomic_json(folder / "selection.json", {"scenario": scenario})
                # Re-running upstream invalidates downstream results and selections.
                index = STAGES.index(stage)
                for later in STAGES[index:]:
                    self.state["stages"][later] = {"status": "pending"}
                    (folder / f"{later}.json").unlink(missing_ok=True)
                if stage == "scenarios":
                    (folder / "selection.json").unlink(missing_ok=True)
            self.active_id = run_id
            self.active_stage = stage
            self.stop.clear()
            self._begin_activity(stage, folder)
            self._activity_log("Execution started", config)
            stages = STAGES if stage == "all" else (stage,)
            self.thread = threading.Thread(
                target=self._run, args=(stages, folder, config), daemon=True
            )
            self.thread.start()
            return run_id

    def _run(self, stages, folder: Path, config: dict):
        try:
            for stage in stages:
                if self.stop.is_set():
                    break
                with self.lock:
                    self.active_stage = stage
                    self.state["activity"].update(current_stage=stage, phase="Starting stage")
                    self.state["stages"][stage] = {"status": "running", "started": time.time()}
                    if stage in {"scenarios", "evaluation"}:
                        self.state["stages"][stage]["timeout"] = config.get("timeout", 300)
                        self.state["stages"][stage]["timeout_scope"] = (
                            "request" if stage == "scenarios" else "evaluation"
                        )
                    if stage == "scenarios":
                        self.state["stages"][stage]["generation_options"] = scenario_options(
                            config
                        )
                    roles = {
                        "scenarios": ("scenario",),
                        "artifact": ("artifact",),
                        "evaluation": ("target", "judge"),
                    }.get(stage, ())
                    self.state["stages"][stage]["models"] = {
                        role: {
                            key: value
                            for key, value in model_connection(config, role).items()
                            if key != "api_key"
                        }
                        for role in roles
                    }
                    self._activity_log("Stage started", config)
                    for role, model in self.state["stages"][stage]["models"].items():
                        self._activity_log(
                            f"Model ({role}): {model['provider']} · {model['model']}", config
                        )
                    if stage == "scenarios":
                        self._activity_log(
                            "Generation options: " + json.dumps(scenario_options(config)), config
                        )
                    if stage in {"scenarios", "evaluation"}:
                        self._activity_log(
                            f"Timeout: {config.get('timeout', 300)}s "
                            + (
                                "per request; retries may add time."
                                if stage == "scenarios"
                                else "for the complete target + judge evaluation."
                            ),
                            config,
                        )
                env = {**os.environ, "ASAGO_DEMO_CONFIG": json.dumps(config)}
                with self.lock:
                    if self.stop.is_set():
                        break
                    self.process = subprocess.Popen(
                        self.command(stage, folder),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        env=env,
                        cwd=self.root.parent,
                        start_new_session=True,
                    )
                for line in self.process.stdout:
                    self._activity_log(line, config, output=True)
                returncode = self.process.wait()
                with self.lock:
                    self.process = None
                    info = self.state["stages"][stage]
                    info["ended"] = time.time()
                    if self.stop.is_set():
                        info["status"] = "cancelled"
                        break
                    path = folder / f"{stage}.json"
                    result = json.loads(path.read_text()) if path.exists() else {}
                    result = redact_value(result, config)
                    if path.exists():
                        atomic_json(path, result)
                    if returncode or result.get("status") != "completed":
                        info.update(
                            status="failed",
                            error=result.get("error")
                            or "The stage stopped without a valid result. See the run log.",
                        )
                        self.state["status"] = "failed"
                        self.state["activity"]["error"] = info["error"]
                        self._activity_log("Stage failed: " + info["error"], config)
                        return
                    info["status"] = "completed"
                    self._activity_log(
                        f"Stage completed in {info['ended'] - info['started']:.1f}s", config
                    )
        except Exception as exc:
            with self.lock:
                self.state["status"] = "failed"
                error = self.redact(str(exc), config)
                self.state["error"] = error
                self.state["activity"]["error"] = error
                for info in self.state["stages"].values():
                    if info["status"] == "running":
                        info.update(status="failed", error=error, ended=time.time())
                self._activity_log("Stage failed: " + error, config)
        finally:
            with self.lock:
                if self.stop.is_set():
                    self.state["status"] = "cancelled"
                    for info in self.state["stages"].values():
                        if info["status"] == "running":
                            info.update(status="cancelled", ended=time.time())
                elif self.state["status"] == "running":
                    self.state["status"] = "completed"
                self.state["activity"].update(status=self.state["status"], ended=time.time())
                self._activity_log("Execution " + self.state["status"], config)

    def cancel(self, run_id=None, stage=None):
        with self.lock:
            if run_id is not None and (run_id != self.active_id or not self.busy):
                return False
            if stage not in (None, "all", self.active_stage):
                return False
            self.stop.set()
            process = self.process
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                threading.Thread(target=self._kill_later, args=(process,), daemon=True).start()
            return True

    @staticmethod
    def _kill_later(process):
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
