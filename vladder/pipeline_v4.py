from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .pipeline_graph import load_pipeline_graph, write_pipeline_dot, write_pipeline_graph
from .pipeline_search import search_pipeline_graph, transformed_pipeline_dict
from .pipeline_verification import attribution_report, infer_affected_fraction, verify_pipeline_plan
from .report import write_csv, write_json


def analyze_pipeline_v4(manifest: Path, out_dir: Path) -> dict[str, Any]:
    graph = load_pipeline_graph(manifest.resolve())
    analysis = out_dir / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    write_pipeline_graph(analysis / "pipeline_graph.json", graph)
    write_pipeline_dot(analysis / "pipeline_graph.dot", graph)
    summary = {
        "schema_version": "vladder-pipeline-analysis-v4.0",
        "pipeline": graph.pipeline,
        "manifest_hash": graph.manifest_hash,
        "graph_hash": graph.graph_hash,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "topological_stage_count": len(graph.annotations["topological_stages"]),
        "max_live_logical_bytes": graph.annotations["max_live_logical_bytes"],
        "information_movement": graph.annotations["information_movement"],
        "profile_weights_measured": graph.annotations["profile_weights_measured"],
    }
    write_json(analysis / "summary.json", summary)
    return summary


def optimize_pipeline_v4(manifest: Path, out_dir: Path, beam_width: int = 24, max_depth: int = 5, child_budget: int = 64, ggml_graph: Path | None = None, profile_report: Path | None = None) -> dict[str, Any]:
    analyze_pipeline_v4(manifest, out_dir)
    graph = load_pipeline_graph(manifest.resolve())
    grammar_dir = Path(__file__).resolve().parent / "grammars/pipeline-v4"
    search = search_pipeline_graph(graph, grammar_dir, beam_width, max_depth, child_budget)
    candidates = []
    for plan in search.plans:
        proof = verify_pipeline_plan(graph, plan)
        attribution = attribution_report(graph, plan)
        candidates.append({
            "plan": asdict(plan), "proof": proof.to_dict(), "attribution": attribution,
            "status": "VERIFIED_STATIC" if proof.status == "proved" else "PROOF_FAIL",
            "measurement_status": "NOT_RUN",
        })
    passing = [candidate for candidate in candidates if candidate["status"] == "VERIFIED_STATIC"]
    passing.sort(key=lambda item: (item["plan"]["score"], item["plan"]["id"]))
    winner = passing[0] if passing else None
    if winner:
        selected = next(plan for plan in search.plans if plan.id == winner["plan"]["id"])
        before = graph.to_dict()
        after = transformed_pipeline_dict(graph, selected)
        write_json(out_dir / "pipeline_graph.before.json", before)
        write_json(out_dir / "pipeline_graph.after.json", after)
        write_pipeline_dot(out_dir / "pipeline_graph.before.dot", graph)
        write_pipeline_dot(out_dir / "pipeline_graph.after.dot", graph, set(selected.streamed_edges))
    v3_region = 1.0 + 6.19195046439629 / 100.0
    v3_model = 1.0 + 0.6034533556480648 / 100.0
    v3_inferred = infer_affected_fraction(v3_region, v3_model)
    authoritative = None
    if ggml_graph is not None:
        raw_graph = json.loads(ggml_graph.read_text())
        graph_model = raw_graph.get("provenance", {}).get("model_sha256")
        manifest_model = graph.provenance.get("model", {}).get("sha256")
        if graph_model != manifest_model:
            raise ValueError("authoritative ggml graph model hash differs from pipeline manifest")
        authoritative = {
            "status": "PASS", "path": str(ggml_graph.resolve()), "graph_hash": raw_graph["graph_hash"],
            "compute_node_count": raw_graph["annotations"]["compute_node_count"],
            "edge_count": raw_graph["annotations"]["edge_count"], "layer_count": raw_graph["annotations"]["layer_count"],
            "operation_counts": raw_graph["annotations"]["operation_counts"],
            "pipeline_categories": raw_graph["annotations"]["qwen_pipeline_categories"],
            "v3_add_rms_mul_regions": raw_graph["annotations"]["v3_add_rms_mul_regions"],
        }
    measured_attribution = None
    if profile_report is not None:
        profile = json.loads(profile_report.read_text())
        if authoritative is None:
            raise ValueError("profile attribution requires an authoritative ggml graph")
        if profile.get("provenance", {}).get("normalized_graph_hash") != authoritative["graph_hash"]:
            raise ValueError("profile report and authoritative ggml graph hashes differ")
        measured_attribution = {
            "status": "PASS", "path": str(profile_report.resolve()),
            "exclusive_graph_us": profile["exclusive_graph_us"], "categories": profile["categories"],
            "stage1_to_stage3_addressable": profile["stage1_to_stage3_addressable"],
        }
    report = {
        "schema_version": "vladder-pipeline-report-v4.0",
        "pipeline": graph.pipeline,
        "manifest_hash": graph.manifest_hash,
        "graph_hash": graph.graph_hash,
        "grammar_hash": search.grammar_hash,
        "authoritative_ggml_graph": authoritative or {"status": "NOT_PROVIDED"},
        "measured_baseline_attribution": measured_attribution or {"status": "NOT_PROVIDED"},
        "search": search.to_dict(),
        "winner": winner,
        "candidates": candidates,
        "physical_measurement": {
            "status": "NOT_RUN",
            "reason": "initial V4 workflow validates IR, search, proof, and attribution; no new production realization has been compiled",
        },
        "v3_empirical_context": {
            "regional_speedup": v3_region,
            "model_point_speedup": v3_model,
            "inferred_affected_fraction_point_estimate": v3_inferred,
            "claimable": False,
            "reason": "model-level confidence interval crossed zero, so inverse Amdahl attribution is diagnostic only",
        },
        "milestones": {
            "pipeline_ir": "PASS",
            "hierarchical_static_search": "PASS",
            "structural_verification": "PASS" if winner else "FAIL",
            "addressable_decode_coverage_25pct": "PASS" if measured_attribution and measured_attribution["stage1_to_stage3_addressable"]["addressable_coverage_25pct"] else "OPEN",
            "synthesized_measured_decode_coverage_25pct": "OPEN",
            "verified_model_speedup_5pct": "OPEN",
            "whole_transformer_block_synthesis": "OPEN",
        },
        "claim": "Best statically ranked structurally verified candidate in the bounded pipeline-v4 grammar; no physical speedup or global optimality claim.",
    }
    write_json(out_dir / "pipeline_report.json", report)
    write_json(out_dir / "search_audit.json", search.to_dict())
    write_csv(out_dir / "pipeline_candidates.csv", [{
        "candidate": item["plan"]["id"], "status": item["status"], "score": item["plan"]["score"],
        "dram_bytes": item["plan"]["cost"]["dram_bytes"], "llc_bytes": item["plan"]["cost"]["llc_bytes"],
        "scratch_bytes": item["plan"]["cost"]["scratch_bytes"], "streamed_edges": ";".join(item["plan"]["streamed_edges"]),
    } for item in candidates])
    return report
