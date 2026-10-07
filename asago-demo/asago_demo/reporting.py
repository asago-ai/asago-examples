"""Reuse PR #79's reporting modules without replacing the pinned extraction engine."""

import base64
import importlib.util
import io
import re
import sys
from functools import lru_cache
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
PR_PACKAGE = ROOT / ".cache/policy-report/src/asago_policy_mapper"
PDF_PREVIEW_LOCK = Lock()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def report_module():
    themes = load_module(
        "asago_policy_mapper.extract.report_themes", PR_PACKAGE / "extract/report_themes.py"
    )
    # Use the exact PR mappings; do not silently fall back to an older package's data.
    from asago_policy_mapper.evals.eval import _load_risk_to_category_map

    themes._load_risk_to_category_map = lambda: _load_risk_to_category_map(
        PR_PACKAGE / "data/risk_to_category.sssom.tsv"
    )
    return load_module("asago_demo_report", PR_PACKAGE / "extract/report.py")


def build_policy_report(data, output):
    pdf = Path(output).with_name("policy.pdf")
    if pdf.is_file():
        build_policy_document(pdf)
    path = report_module().build_risk_extraction_report(data, output)
    # The local preview isolates reports from the job-control API. Opaque-origin
    # frames cannot persist preferences; retain the PR's default and local toggle.
    html = customize_policy_header(path.read_text())
    html = html.replace(
        "const saved = localStorage.getItem('rl-dark-mode');",
        "let saved = null; try { saved = localStorage.getItem('rl-dark-mode'); } catch (_) {}",
    ).replace(
        "localStorage.setItem('rl-dark-mode', String(dark));",
        "try { localStorage.setItem('rl-dark-mode', String(dark)); } catch (_) {}",
    )
    path.write_text(html)
    return path


def customize_policy_header(html):
    """Adapt the pinned report header while retaining its interactive report body."""
    before, marker, rest = html.partition('<header class="asago-header">')
    if not marker:
        return html
    header, end, after = rest.partition("</header>")
    header = re.sub(
        r'<div[^>]*>\s*<img[^>]*class="asago-logo"[^>]*>\s*'
        r"<span[^>]*>Policy mapper</span>\s*</div>",
        "",
        header,
    )
    header = re.sub(
        r'<h1[^>]*>Policy risk report</h1>\s*<p[^>]*x-text="docNames"[^>]*></p>',
        '<h1 class="report-font-semibold report-tracking-tight report-break-all" '
        'style="font-size: clamp(1.75rem, 3vw, 2.5rem)">'
        '<a href="document.html" target="_blank" rel="noopener noreferrer" '
        'title="Open policy PDF in a new tab" '
        'style="color: #7eb0ff; text-decoration: underline; '
        'text-decoration-thickness: 1px; text-underline-offset: .18em">'
        "FS-ISAC generative AI</a></h1>",
        header,
    )
    header = header.replace('href="policy.pdf"', 'href="document.html"')
    return before + marker + header + end + after


def build_policy_document(pdf):
    """Render the source PDF for browsers without a native PDF viewer."""
    import pypdfium2 as pdfium

    output = pdf.with_name("document.html")
    # PDFium is not thread-safe; report requests can arrive concurrently.
    with PDF_PREVIEW_LOCK:
        if output.is_file() and output.stat().st_mtime >= pdf.stat().st_mtime:
            return output
        pages = []
        with pdfium.PdfDocument(pdf) as document:
            count = len(document)
            for index in range(count):
                page = document[index]
                try:
                    bitmap = page.render(scale=2)
                    try:
                        with bitmap.to_pil() as image, io.BytesIO() as buffer:
                            image.save(buffer, format="WEBP", quality=90)
                            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                pages.append(
                    f'<figure id="page-{index + 1}"><figcaption>Page {index + 1} of '
                    f'{count}</figcaption><img src="data:image/webp;base64,{encoded}" '
                    f'alt="Original policy PDF, page {index + 1}" loading="lazy"></figure>'
                )
        html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FS-ISAC generative AI · Policy PDF</title><style>
*{box-sizing:border-box}body{margin:0;background:#e8edf3;color:#142139;
font-family:system-ui,sans-serif}header{position:sticky;top:0;display:flex;
align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;
padding:1rem 1.5rem;background:#fff;border-bottom:1px solid #cbd5e1}
h1{font-size:1.25rem;margin:0}a{color:#1759bb;text-underline-offset:.2em}
main{max-width:1000px;margin:auto;padding:1.25rem}figure{margin:0 0 2rem}
figcaption{padding:.5rem 0;color:#475569;font-size:.875rem}
img{display:block;width:100%;height:auto;background:white;box-shadow:0 2px 10px #0002}
</style></head><body><header><h1>FS-ISAC generative AI</h1>
<a href="policy.pdf" download="fs-isac.pdf">Download original PDF</a></header><main>"""
        output.write_text(html + "".join(pages) + "</main></body></html>")
    return output
