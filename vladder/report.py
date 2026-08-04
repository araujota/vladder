from __future__ import annotations

from html import escape
import json
from pathlib import Path


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = [
            "candidate",
            "status",
            "ns_per_item",
            "ci95_ns_per_item",
            "speedup_vs_baseline_pct",
            "code_size_bytes",
            "instruction_count",
            "tags",
            "proof_status",
        ]
    lines = [",".join(fields)]
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, (list, tuple)):
                value = "|".join(str(v) for v in value)
            if isinstance(value, dict):
                value = json.dumps(value, sort_keys=True)
            text = str(value)
            if "," in text or '"' in text:
                text = '"' + text.replace('"', '""') + '"'
            values.append(text)
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n")


def write_html(path: Path, report: dict[str, object]) -> None:
    rows = report["candidates"]
    best = report.get("winner") or {}
    table = "\n".join(
        "<tr>"
        f"<td>{escape(str(r.get('candidate', '')))}</td>"
        f"<td>{escape(str(r.get('status', '')))}</td>"
        f"<td>{escape(str(r.get('ns_per_item', '')))}</td>"
        f"<td>{escape(str(r.get('speedup_vs_baseline_pct', '')))}</td>"
        f"<td>{escape(str(r.get('code_size_bytes', '')))}</td>"
        f"<td>{escape(str(r.get('instruction_count', '')))}</td>"
        f"<td>{escape(' '.join(r.get('tags', [])))}</td>"
        "</tr>"
        for r in rows
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>vLadder Report</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ margin-top: 28px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; max-width: 900px; }}
    .metric {{ border: 1px solid #d5d9df; border-radius: 6px; padding: 12px; }}
    .label {{ color: #596579; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .value {{ font-size: 22px; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px; text-align: left; }}
    th {{ background: #f6f8fa; }}
    code {{ background: #f6f8fa; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>vLadder Optimization Report</h1>
  <p><code>{escape(str(report.get("source", "")))}</code> :: <code>{escape(str(report.get("function", "")))}</code></p>
  <div class="summary">
    <div class="metric"><div class="label">Winner</div><div class="value">{escape(str(best.get("candidate", "none")))}</div></div>
    <div class="metric"><div class="label">Original</div><div class="value">{escape(str(report.get("baseline_ns_per_item", "n/a")))} ns/item</div></div>
    <div class="metric"><div class="label">Optimized</div><div class="value">{escape(str(best.get("ns_per_item", "n/a")))} ns/item</div></div>
    <div class="metric"><div class="label">Speedup</div><div class="value">{escape(str(best.get("speedup_vs_baseline_pct", "0")))}%</div></div>
  </div>
  <h2>Environment</h2>
  <p>{escape(str(report.get("cpu_model", "")))}<br>{escape(str(report.get("compiler", "")))}</p>
  <h2>Candidates</h2>
  <table>
    <thead><tr><th>Candidate</th><th>Status</th><th>ns/item</th><th>Speedup %</th><th>Code bytes</th><th>Instructions</th><th>Tags</th></tr></thead>
    <tbody>{table}</tbody>
  </table>
  <h2>Verification</h2>
  <p>{escape(str(report.get("verification_summary", "")))}</p>
  <h2>Reproducibility</h2>
  <p>Command: <code>{escape(str(report.get("command", "")))}</code></p>
</body>
</html>
"""
    path.write_text(html)
