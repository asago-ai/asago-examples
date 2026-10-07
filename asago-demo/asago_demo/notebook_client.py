"""Notebook controls use the same local server as the recording interface."""

import json
import time
import urllib.error
import urllib.request


class DemoClient:
    def __init__(self, base_url="http://127.0.0.1:8765"):
        self.base_url = base_url
        self.run_id = None

    def request(self, route, data=None):
        request = urllib.request.Request(
            self.base_url + route,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", "X-Asago-Demo": "1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(json.load(exc).get("error", str(exc))) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Start the local demo with ./asago-demo/launch.sh first.") from exc

    def connect(self):
        data = self.request("/api/state")
        self.run_id = data.get("active_id") or next((r["id"] for r in data["history"]), None)
        print("Connected to", self.base_url)
        print("Model:", data["settings"].get("model"))
        print("Selected run:", self.run_id or "new run")
        return self

    def run(self, stage, scenario=""):
        result = self.request(
            "/api/start", {"stage": stage, "run": self.run_id, "scenario": scenario}
        )
        self.run_id = result["run_id"]
        print("Run:", self.run_id)
        last_logs = []
        try:
            while True:
                data = self.request("/api/state?run=" + self.run_id)
                state = data["run"]
                logs = state.get("logs", [])
                if logs != last_logs:
                    overlap = next(
                        (
                            n
                            for n in range(min(len(logs), len(last_logs)), 0, -1)
                            if last_logs[-n:] == logs[:n]
                        ),
                        0,
                    )
                    for line in logs[overlap:]:
                        print(line)
                    last_logs = logs
                status = state["status"] if stage == "all" else state["stages"][stage]["status"]
                if status not in {"pending", "running"}:
                    if status != "completed":
                        raise RuntimeError(f"Stage {status}; inspect the dashboard or log.")
                    return state["results"].get(stage, state["results"])
                time.sleep(1)
        except KeyboardInterrupt:
            self.request("/api/cancel", {"run": self.run_id, "stage": stage})
            raise

    def show_policy(self, result):
        from IPython.display import IFrame, display

        display(
            IFrame(
                self.base_url + "/files/" + self.run_id + "/" + result["report"],
                width="100%",
                height=1000,
            )
        )

    def show_scenarios(self, result):
        import pandas as pd
        from IPython.display import display

        display(
            pd.DataFrame(
                [
                    {k: item.get(k) for k in ("id", "title", "risk_id", "surface", "file")}
                    for item in result["scenarios"]
                ]
            )
        )

    def show_artifact(self, result):
        from IPython.display import JSON, display

        print("Coverage:", result["coverage"])
        display(JSON(result["validation"]))
        display(JSON(result["artifact"]))

    def show_evaluation(self, result):
        from IPython.display import JSON, display

        print("Target:", result["target_model"], "—", result["outcome"].replace("_", " "))
        display(JSON(result["attempts"]))
        print(
            "Garak report:", self.base_url + "/files/" + self.run_id + "/" + result["report_file"]
        )
