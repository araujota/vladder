#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from vladder.automatic import inspect_automatic_region
from vladder.cpp_regions import isolate_cpp_region
from vladder.rust_adapter import RustRegionRequest, inspect_rust_region


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run_demos(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    demos: list[dict[str, Any]] = []

    c_source = root / "examples" / "automatic_regions" / "supported_pointwise.c"
    c_support = inspect_automatic_region(c_source, "transform", output / "c-pointwise")
    demos.append({
        "id": "c-pointwise-capture",
        "status": "pass" if c_support.supported else "fail",
        "language": "c",
        "evidence": c_support.to_dict(),
        "claim": "bounded C region classification; no physical speedup claim",
    })

    cpp_source = root / "examples" / "cpp_regions" / "accepted_byte_parser.cpp"
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if compiler is None:
        demos.append({"id": "cpp-aggregate-closure", "status": "fail", "reason": "clang++ unavailable"})
    else:
        compile_db = output / "cpp-aggregate-closure" / "compile_commands.json"
        _write(compile_db, [{
            "directory": str(root),
            "file": str(cpp_source),
            "arguments": [compiler, "-std=c++20", "-O2", "-c", str(cpp_source), "-o", str(output / "parser.o")],
        }])
        _, cpp_report = isolate_cpp_region(
            cpp_source, "parse_word", compile_db, output / "cpp-aggregate-closure" / "artifacts",
        )
        closure_proof = cpp_report.get("region_closure_proof", {})
        demos.append({
            "id": "cpp-aggregate-closure",
            "status": "pass" if cpp_report.get("status") == "supported" and closure_proof.get("status") == "PASS" else "fail",
            "language": "cpp",
            "support_tier": cpp_report.get("support_tier"),
            "closure_classes": cpp_report.get("region_closure", {}).get("classes", {}),
            "proof_status": closure_proof.get("status"),
            "claim": "aggregate/exit/helper representation closure; no owning-wrapper or performance claim",
        })

    rust_root = root / "examples" / "rust_regions" / "byte_count"
    rust_report = inspect_rust_region(RustRegionRequest(
        manifest_path=rust_root / "Cargo.toml",
        source=rust_root / "src" / "lib.rs",
        function="count_equal",
        output_directory=output / "rust-byte-count",
        proof_bound=8,
    ))
    demos.append({
        "id": "rust-byte-count-capture",
        "status": "pass" if rust_report.get("status") == "supported" else "fail",
        "language": "rust",
        "semantic_graph": bool(rust_report.get("semantic_graph", {}).get("nodes")),
        "support_version": rust_report.get("support_version"),
        "claim": "one monomorphic borrowed-slice specialization; no arbitrary Rust or performance claim",
    })

    report = {
        "schema_version": "vladder-release-demos-v1",
        "status": "pass" if len(demos) == 3 and all(item["status"] == "pass" for item in demos) else "fail",
        "demo_count": len(demos),
        "demos": demos,
    }
    _write(output / "release-demos.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run three small release-grade vLadder demos")
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", default="release-validation/demos")
    args = parser.parse_args()
    report = run_demos(Path(args.root), Path(args.out_dir))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
