from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from .flow import _normalize_ir, llvm_ir_stats
from .llvm_ir import extract_output_slice
from .operator_contract import OperatorContract, load_contract
from .operator_graph import OperatorGraph, build_operator_graph, write_operator_graph
from .toolchain import compiler_version, cpu_model, run
from .toolchain import discover_toolchain
from .hardware_manifest import capture_manifest, stability_warnings, write_manifest


def analyze_operator(source: Path, contract_path: Path, out_dir: Path, target_name: str = "local", cpu: int = 0) -> tuple[OperatorContract, OperatorGraph, dict[str, Any]]:
    contract = load_contract(contract_path)
    source = source.resolve()
    out_dir = out_dir.resolve()
    analysis_dir = out_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    manifest = capture_manifest(target_name, cpu, discover_toolchain())
    write_manifest(analysis_dir / "hardware_manifest.json", manifest)
    ir_info = _lower_operator(source, contract, analysis_dir)
    output_indices = contract.output_parameter_indices
    slice_ = extract_output_slice(Path(ir_info["analysis_ir"]), contract.entrypoint, output_indices)
    graph = build_operator_graph(contract, source_hash, {**ir_info, "slice_roots": slice_.roots, "slice_invariants": slice_.invariants})
    (analysis_dir / "contract.json").write_text(json.dumps(contract.to_dict(), indent=2, sort_keys=True) + "\n")
    (analysis_dir / "operator_slice.json").write_text(json.dumps(slice_.to_dict(), indent=2, sort_keys=True) + "\n")
    write_operator_graph(analysis_dir / "operator_graph.json", graph)
    summary = {
        "operator": contract.name,
        "entrypoint": contract.entrypoint,
        "contract_hash": contract.contract_hash,
        "graph_hash": graph.graph_hash,
        "source_hash": source_hash,
        "source": str(source),
        "contract": str(contract.path),
        "output_argument_indices": list(output_indices),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "stateful_sccs": graph.annotations["stateful_sccs"],
        "fusion_regions": graph.annotations["fusion_regions"],
        "ir": ir_info,
        "hardware_manifest_hash": manifest.manifest_hash,
        "hardware_warnings": stability_warnings(manifest),
    }
    (out_dir / "operator_analysis.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return contract, graph, summary


def _lower_operator(source: Path, contract: OperatorContract, analysis_dir: Path) -> dict[str, Any]:
    if contract.language == "restricted-c++20":
        compiler = shutil.which("clang++-20") or shutil.which("clang++")
        language_flags = ["-std=c++20", "-fno-exceptions", "-fno-rtti"]
    else:
        compiler = shutil.which("clang-20") or shutil.which("clang")
        language_flags = ["-std=c17"]
    if not compiler:
        raise RuntimeError(f"no Clang compiler for {contract.language}")
    raw = analysis_dir / "operator.raw.ll"
    normalized = analysis_dir / "operator.normalized.ll"
    flags = [*language_flags, "-O1", "-march=native", "-fno-vectorize", "-fno-slp-vectorize", "-fno-unroll-loops"]
    result = run([compiler, *flags, "-S", "-emit-llvm", str(source), "-o", str(raw)], timeout=180)
    if result.returncode != 0:
        raise RuntimeError("operator LLVM lowering failed:\n" + (result.stdout + result.stderr)[-4000:])
    raw_text = raw.read_text(errors="replace")
    function_ir = _normalize_ir(raw_text, contract.entrypoint)
    if not function_ir.strip():
        raise RuntimeError(f"entrypoint {contract.entrypoint} was not emitted with an unmangled name; use extern \"C\" for C++")
    normalized.write_text(function_ir)
    triple = re.search(r'^target triple = "([^"]+)"', raw_text, re.MULTILINE)
    return {
        "compiler": compiler,
        "compiler_version": compiler_version(compiler),
        "flags": flags,
        "target_triple": triple.group(1) if triple else "unknown",
        "target_cpu": cpu_model(),
        "raw_ir": str(raw),
        "analysis_ir": str(normalized),
        "stats": llvm_ir_stats(normalized),
    }
