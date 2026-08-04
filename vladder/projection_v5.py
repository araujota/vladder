from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .projection_graph import emit_projection_dot, load_projection_graph
from .projection_layout import interleave_sibling_blocks, verify_layout_round_trip
from .projection_search import search_projection_graph
from .projection_verification import verify_projection_plan


ROOT = Path(__file__).resolve().parent


def analyze_projection_v5(manifest: Path, out_dir: Path) -> dict[str, Any]:
    graph = load_projection_graph(manifest)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "projection_graph.json").write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")
    (out_dir / "projection_graph.dot").write_text(emit_projection_dot(graph))
    report = {
        "schema_version": "vladder-projection-analysis-v5.0",
        "complex": graph.complex, "graph_hash": graph.graph_hash,
        "annotations": graph.annotations, "physical_measurement": {"status": "NOT_RUN"},
    }
    (out_dir / "analysis.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def synthesize_projection_v5(manifest: Path, out_dir: Path, beam_width: int = 32, max_depth: int = 7, child_budget: int = 64) -> dict[str, Any]:
    graph = load_projection_graph(manifest)
    search = search_projection_graph(graph, ROOT / "grammars" / "projection-v5", beam_width, max_depth, child_budget)
    admitted = []
    for plan in search.plans:
        proof = verify_projection_plan(graph, plan)
        if proof.status == "proved":
            admitted.append((plan, proof))
    if not admitted:
        raise RuntimeError("projection search produced no verified plan")
    winner, proof = min(admitted, key=lambda item: (item[0].score, item[0].id))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "projection_graph.json").write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")
    (out_dir / "projection_graph.dot").write_text(emit_projection_dot(graph))
    (out_dir / "search_audit.json").write_text(json.dumps(search.to_dict(), indent=2, sort_keys=True) + "\n")
    with (out_dir / "projection_candidates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "score", "rules", "token_tile", "sequence_tile", "shared_preparation", "layout", "child_status"])
        writer.writeheader()
        for plan in search.plans:
            writer.writerow({"id": plan.id, "score": plan.score, "rules": ";".join(plan.rules), "token_tile": plan.token_tile, "sequence_tile": plan.sequence_tile, "shared_preparation": plan.shared_preparation, "layout": plan.layout, "child_status": plan.child_status})
    report = {
        "schema_version": "vladder-projection-synthesis-v5.0",
        "claim": "best verified static realization found in the bounded projection grammar; no physical performance claim",
        "complex": graph.complex, "graph_hash": graph.graph_hash, "grammar_hash": search.grammar_hash,
        "search": {"status": search.status, "explored": search.explored, "beam_width": search.beam_width, "max_depth": search.max_depth, "child_budget": search.child_budget},
        "winner": {"plan": _asdict(winner), "proof": proof.to_dict(), "status": "static_verified"},
        "physical_measurement": {"status": "NOT_RUN", "reason": "candidate has not been lowered into llama.cpp or benchmarked"},
        "model_verification": {"status": "NOT_RUN"},
        "portfolio_ranking": {"status": "NOT_RUN"},
    }
    (out_dir / "projection_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def transform_projection_layout_v5(inputs: list[Path], block_bytes: int, out_dir: Path) -> dict[str, Any]:
    payloads = [path.read_bytes() for path in inputs]
    transformed, manifest = interleave_sibling_blocks(payloads, block_bytes)
    proof = verify_layout_round_trip(payloads, transformed, manifest)
    if proof["status"] != "proved":
        raise RuntimeError("exact layout inverse verification failed")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transformed-layout.bin").write_bytes(transformed)
    report = {
        "schema_version": "vladder-layout-transform-v5.0",
        "inputs": [str(path.resolve()) for path in inputs], "layout_manifest": manifest,
        "proof": proof, "numerical_change": False,
    }
    (out_dir / "layout-manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _asdict(value: Any) -> dict[str, Any]:
    from dataclasses import asdict
    return asdict(value)
