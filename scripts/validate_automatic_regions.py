#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


SUPPORTED = {
    "supported_pointwise.c": "pointwise_map",
    "supported_guarded.c": "guarded_pointwise_map",
    "supported_stencil.c": "stencil",
    "supported_scan.c": "scan",
    "supported_recurrence.c": "recurrence",
    "supported_indirect.c": "indirect_memory",
}
ADAPTERS = {
    "adapter_external_call.c": "external-call-adapter",
    "adapter_multi_loop.c": "loop-shape-adapter",
    "adapter_wrong_abi.c": "abi-adapter",
    "adapter_control_flow.c": "control-flow-adapter",
}


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate vLadder's automatic bounded-region workflow")
    parser.add_argument("--workspace", type=Path, default=Path("examples/automatic_regions"))
    parser.add_argument("--out-dir", type=Path, default=Path("build/automatic-region-validation"))
    parser.add_argument("--python", default=sys.executable, help="Python interpreter containing the vLadder package")
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--inner", type=int, default=2)
    args = parser.parse_args()

    project = Path(__file__).resolve().parent.parent
    workspace = args.workspace.resolve()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cpu = args.cpu
    if cpu is None:
        affinity = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else {0}
        cpu = min(affinity)

    results: list[dict[str, object]] = []
    failed = False
    for filename, family in SUPPORTED.items():
        target = output / Path(filename).stem
        command = [
            args.python,
            "-m",
            "vladder",
            "region",
            "optimize",
            "--source",
            str(workspace / filename),
            "--function",
            "transform",
            "--out-dir",
            str(target),
            "--n",
            "2048",
            "--reps",
            str(args.reps),
            "--inner",
            str(args.inner),
            "--cpu",
            str(cpu),
            "--min-speedup-pct",
            "1000",
        ]
        completed = run(command, project)
        report_path = target / "perf.json"
        errors: list[str] = []
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        automatic = report.get("automatic_region", {})
        if completed.returncode != 0:
            errors.append(f"command returned {completed.returncode}: {(completed.stderr + completed.stdout)[-1000:]}")
        if automatic.get("status") != "supported" or automatic.get("family") != family:
            errors.append(f"support mismatch: {automatic}")
        rows = [row for row in report.get("candidates", []) if "automatic-region" in row.get("tags", [])]
        if not rows:
            errors.append("no generated automatic candidate")
        for row in rows:
            if row.get("status") != "PASS":
                errors.append(f"{row.get('candidate')} status={row.get('status')}")
            if row.get("proof", {}).get("status") != "PROVED":
                errors.append(f"{row.get('candidate')} structural proof incomplete")
            if row.get("memory_proof", {}).get("status") != "proved":
                errors.append(f"{row.get('candidate')} memory proof incomplete")
            if row.get("alive2", {}).get("status") != "correct":
                errors.append(f"{row.get('candidate')} Alive2 status={row.get('alive2', {}).get('status')}")
        result = {
            "fixture": filename,
            "family": family,
            "status": "pass" if not errors else "fail",
            "errors": errors,
            "automatic_candidates": [
                {
                    "candidate": row.get("candidate"),
                    "status": row.get("status"),
                    "speedup_vs_baseline_pct": row.get("speedup_vs_baseline_pct"),
                    "proof": row.get("proof", {}).get("status"),
                    "memory": row.get("memory_proof", {}).get("status"),
                    "alive2": row.get("alive2", {}).get("status"),
                }
                for row in rows
            ],
        }
        results.append(result)
        failed |= bool(errors)
        print(f"{filename}: {result['status']}")

    for filename, adapter in ADAPTERS.items():
        target = output / Path(filename).stem
        completed = run(
            [
                args.python,
                "-m",
                "vladder",
                "region",
                "inspect",
                "--source",
                str(workspace / filename),
                "--function",
                "transform",
                "--out-dir",
                str(target),
            ],
            project,
        )
        support_path = target / "automatic-support.json"
        support = json.loads(support_path.read_text()) if support_path.exists() else {}
        actual = (support.get("adapters") or [{}])[0].get("kind")
        errors = []
        if completed.returncode != 2:
            errors.append(f"inspect returned {completed.returncode}, expected 2")
        if support.get("status") != "adapter_required" or actual != adapter:
            errors.append(f"adapter mismatch: expected {adapter}, got {actual}")
        results.append({"fixture": filename, "status": "pass" if not errors else "fail", "adapter": actual, "errors": errors})
        failed |= bool(errors)
        print(f"{filename}: {'pass' if not errors else 'fail'}")

    summary = {
        "schema_version": "vladder-automatic-validation-v1",
        "generated_at_unix": int(time.time()),
        "workspace": str(workspace),
        "python": args.python,
        "cpu": cpu,
        "status": "fail" if failed else "pass",
        "results": results,
    }
    (output / "validation-report.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"validation: {summary['status']} ({output / 'validation-report.json'})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
