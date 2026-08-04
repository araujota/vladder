from __future__ import annotations

from dataclasses import asdict
import csv
import json
from pathlib import Path
from typing import Any

from .kernel_graph import KernelGraph, kernel_graph_from_projection
from .kernel_search import search_kernel_graph
from .projection_graph import load_projection_graph
from .sksf_attribution import AttributionStudy, load_attribution_study


def synthesize_kernel_v6(
    projection_manifest: Path,
    attribution_paths: list[Path],
    grammar_dir: Path,
    out_dir: Path,
    *,
    beam_width: int = 32,
    max_depth: int = 6,
    allow_exploratory: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    studies = _load_studies(attribution_paths)
    projection = load_projection_graph(projection_manifest)
    graph = kernel_graph_from_projection(projection)
    search = search_kernel_graph(
        graph, grammar_dir, studies, beam_width=beam_width, max_depth=max_depth,
        allow_exploratory=allow_exploratory,
    )
    candidates = []
    for candidate in search.candidates:
        item = asdict(candidate)
        item["measurement_status"] = "NOT_RUN"
        item["semantic_status"] = "STRUCTURAL_ONLY"
        candidates.append(item)
    report = {
        "schema_version": "vladder-sksf-v6.0",
        "kernel_graph": graph.to_dict(),
        "attribution_studies": [study.to_dict() for study in studies.values()],
        "search": search.to_dict(),
        "candidates": candidates,
        "claim": "Static SKSF search only. No kernel or portfolio performance claim is permitted until executable candidates pass semantic verification and physical ranking.",
        "open_obligations": [
            "compile retained candidate realizations",
            "prove or differentially verify full quantized-kernel semantics",
            "rank with randomized independent-process hardware measurements",
            "verify generated-token identity and portfolio workload floors",
        ],
    }
    _write_json(out_dir / "kernel-graph.json", graph.to_dict())
    (out_dir / "kernel-graph.dot").write_text(_dot(graph))
    _write_json(out_dir / "grammar-admissions.json", [asdict(item) for item in search.admissions])
    _write_json(out_dir / "search-audit.json", list(search.audit))
    _write_json(out_dir / "sksf-report.json", report)
    _write_candidates(out_dir / "kernel-candidates.csv", candidates)
    return report


def validate_attribution_v6(paths: list[Path], out_path: Path | None = None) -> dict[str, Any]:
    studies = _load_studies(paths)
    report = {
        "schema_version": "vladder-attribution-validation-v6.0",
        "status": "PASS",
        "study_count": len(studies),
        "studies": [study.to_dict() for study in studies.values()],
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(out_path, report)
    return report


def _load_studies(paths: list[Path]) -> dict[str, AttributionStudy]:
    studies = [load_attribution_study(path) for path in paths]
    indexed = {study.id: study for study in studies}
    if len(indexed) != len(studies):
        raise ValueError("attribution study ids must be unique")
    return indexed


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_candidates(path: Path, candidates: list[dict[str, Any]]) -> None:
    fields = ["id", "status", "bounded_optimality", "rules", "families", "guards", "measurement_status", "semantic_status"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({**candidate, "rules": ";".join(candidate["rules"]), "families": ";".join(candidate["families"]), "guards": ";".join(candidate["guards"])})


def _dot(graph: KernelGraph) -> str:
    lines = ["digraph KernelGraph {", "  rankdir=LR;"]
    for node in graph.nodes:
        lines.append(f'  "{node.id}" [label="{node.id}\\n{node.kind}"];')
    for edge in graph.edges:
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{edge.quantization} {edge.logical_bytes} B"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
