from pathlib import Path

import pytest


def test_report_keeps_pr79_interactions_and_tolerates_sandboxed_storage(tmp_path):
    pytest.importorskip("asago_policy_mapper")
    from asago_demo.reporting import build_policy_report

    source = {
        "risks": [
            {
                "risk_id": "atlas-exposing-personal-information",
                "risk_name": "</script><script>injected()</script>",
                "taxonomy": "ibm-risk-atlas",
            }
        ]
    }
    path = build_policy_report(source, tmp_path / "report.html")
    html = Path(path).read_text()
    assert "theme_catalog" in html
    assert "<script>injected()</script>" not in html
    assert "try { saved = localStorage.getItem" in html
    assert "try { localStorage.setItem" in html
