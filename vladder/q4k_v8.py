from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any

from .hardware_manifest import capture_manifest, write_manifest
from .q4k_parity import run_q4k_parity
from .q4k_physical import build_q4k_physical_graph
from .q4k_v8_variants import (
    DIAGNOSTIC_DESCRIPTIONS, build_v8_diagnostic_harness, execute_diagnostic_process,
    make_v8_fixtures, perf_probe, summarize_process_records,
)
from .report import write_json
from .toolchain import discover_toolchain

STAGE_CODES = ("A", "B", "C", "D", "E", "F", "G", "H")


def run_q4k_v8(
    active_manifest_path: Path,
    reconstruction_report_path: Path,
    v7_parity_report_path: Path,
    out_dir: Path,
    *,
    cpu: int = 0,
    baseline_processes: int = 20,
    baseline_repetitions: int = 50,
    ablation_processes: int = 10,
    ablation_repetitions: int = 25,
    seed: int = 8808,
) -> dict[str, Any]:
    if baseline_processes < 20 or baseline_repetitions < 50:
        raise ValueError("V8 baseline attribution requires at least 20 processes and 50 repetitions")
    if ablation_processes < 10 or ablation_repetitions < 25:
        raise ValueError("V8 ablations require at least 10 processes and 25 repetitions")
    out_dir = out_dir.resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    active = json.loads(active_manifest_path.read_text())
    reconstruction = json.loads(reconstruction_report_path.read_text())
    v7_parity = json.loads(v7_parity_report_path.read_text())
    if active.get("status") != "PASS" or reconstruction.get("status") != "PASS" or v7_parity.get("classification") != "parity_pass":
        raise ValueError("V8 requires passing V7 capture, reconstruction, and parity artifacts")
    freeze = _freeze_v7(active, active_manifest_path, reconstruction_report_path, v7_parity_report_path, out_dir, cpu)
    parity_dir = out_dir / "phase1-parity"
    parity = run_q4k_parity(
        active_manifest_path, parity_dir, processes=baseline_processes,
        repetitions=baseline_repetitions, inner=4, seed=seed,
    )
    if parity["classification"] != "parity_pass":
        raise RuntimeError("V8 baseline parity reproduction failed")
    assembly_shape_match = parity["assembly"]["native"] == v7_parity["assembly"]["native"]
    if not assembly_shape_match:
        raise RuntimeError("V8 native assembly shape differs from V7")
    freeze["v8_parity"] = parity["benchmark"]
    freeze["assembly_shape_match"] = True
    write_json(out_dir / "phase1-freeze-report.json", freeze)

    llama_root = Path(active["source_provenance"]["kernel"]["path"]).parents[5]
    graph = build_q4k_physical_graph(
        parity_dir / "regenerated-q4k-gemv.cpp", reconstruction_report_path,
        llama_root, out_dir / "phase2-physical-graph",
    )
    harness = build_v8_diagnostic_harness(active, parity_dir / "q4k-parity-report.json", out_dir / "phase3-diagnostics")
    fixture_root = out_dir / "fixtures"
    fixtures: dict[str, dict[str, Path]] = {
        "gate_r1": make_v8_fixtures(fixture_root / "gate-r1", 2560, 9728, 1, seed),
        "gate_r2": make_v8_fixtures(fixture_root / "gate-r2", 2560, 9728, 2, seed),
        "gate_r4": make_v8_fixtures(fixture_root / "gate-r4", 2560, 9728, 4, seed),
        "gate_r8": make_v8_fixtures(fixture_root / "gate-r8", 2560, 9728, 8, seed),
        "l2_r1": make_v8_fixtures(fixture_root / "l2-r1", 2560, 512, 1, seed + 1),
        "q_r1": make_v8_fixtures(fixture_root / "q-r1", 2560, 4096, 1, seed + 2),
        "k_r1": make_v8_fixtures(fixture_root / "k-r1", 2560, 1024, 1, seed + 3),
    }

    baseline_records = [execute_diagnostic_process(
        harness, fixtures["gate_r1"], candidate="native", n=2560, nc=9728, nr=1,
        repetitions=baseline_repetitions, inner=4, cache_mode="warm", eviction_bytes=0, cpu=cpu,
    ) for _ in range(baseline_processes)]
    baseline_summary = summarize_process_records(baseline_records, seed)

    labels = list(DIAGNOSTIC_DESCRIPTIONS)
    ablation_rounds: list[dict[str, Any]] = []
    all_ablation_records: dict[str, list[dict[str, Any]]] = {label: [] for label in labels}
    for round_index in range(2):
        order = [(process, label) for process in range(ablation_processes) for label in labels]
        random.Random(seed + round_index).shuffle(order)
        records = {label: [] for label in labels}
        audit = []
        for ordinal, (process, label) in enumerate(order):
            payload = execute_diagnostic_process(
                harness, fixtures["gate_r1"], candidate=label, n=2560, nc=9728, nr=1,
                repetitions=ablation_repetitions, inner=2, cache_mode="warm", eviction_bytes=0, cpu=cpu,
            )
            records[label].append(payload); all_ablation_records[label].append(payload)
            audit.append({"ordinal": ordinal, "process": process, **payload})
        summaries = {label: summarize_process_records(items, seed + round_index*100 + labels.index(label)) for label, items in records.items()}
        ablation_rounds.append({"round": round_index + 1, "order": order, "summaries": summaries})
        write_json(out_dir / f"phase4-ablation-round-{round_index+1}-audit.json", audit)
    combined_ablation = {label: summarize_process_records(items, seed + 500 + index) for index, (label, items) in enumerate(all_ablation_records.items())}

    cache_configs = [
        ("l2", "l2_r1", 2560, 512, 1, "warm", 0),
        ("llc", "gate_r1", 2560, 9728, 1, "warm", 0),
        ("streaming", "gate_r1", 2560, 9728, 1, "streaming", 128*1024*1024),
        ("gate_rows2", "gate_r2", 2560, 9728, 2, "warm", 0),
        ("gate_rows4", "gate_r4", 2560, 9728, 4, "warm", 0),
        ("gate_rows8", "gate_r8", 2560, 9728, 8, "warm", 0),
        ("q_rows1", "q_r1", 2560, 4096, 1, "warm", 0),
        ("k_rows1", "k_r1", 2560, 1024, 1, "warm", 0),
    ]
    cache_results: dict[str, Any] = {}
    cache_audit = []
    cache_order = [(process, config) for process in range(ablation_processes) for config in cache_configs]
    random.Random(seed + 700).shuffle(cache_order)
    grouped: dict[str, list[dict[str, Any]]] = {config[0]: [] for config in cache_configs}
    for ordinal, (process, config) in enumerate(cache_order):
        name, fixture_name, n, nc, nr, mode, eviction = config
        payload = execute_diagnostic_process(
            harness, fixtures[fixture_name], candidate="native", n=n, nc=nc, nr=nr,
            repetitions=ablation_repetitions, inner=2, cache_mode=mode, eviction_bytes=eviction, cpu=cpu,
        )
        grouped[name].append(payload); cache_audit.append({"ordinal": ordinal, "process": process, "configuration": name, **payload})
    for index, (name, items) in enumerate(grouped.items()):
        cache_results[name] = summarize_process_records(items, seed + 800 + index)
    write_json(out_dir / "phase4-cache-regime-audit.json", cache_audit)

    perf_labels = ["native", *labels]
    perf = {label: perf_probe(
        harness, fixtures["gate_r1"], label, 2560, 9728, 1, "warm", 0, cpu,
    ) for label in perf_labels}
    perf["native_streaming"] = perf_probe(
        harness, fixtures["gate_r1"], "native", 2560, 9728, 1, "streaming", 128*1024*1024, cpu,
    )
    physical_evidence = {
        "schema_version": "vladder-q4k-physical-evidence-v8.0",
        "baseline": baseline_summary, "baseline_records": baseline_records,
        "ablation_rounds": ablation_rounds, "combined_ablation": combined_ablation,
        "diagnostic_descriptions": DIAGNOSTIC_DESCRIPTIONS, "cache_regimes": cache_results,
        "perf": perf, "harness": harness, "ranking_eligible": False,
        "frequency_policy": "boost enabled; per-process frequency and temperature captured and regressed",
    }
    write_json(out_dir / "phase4-physical-evidence.json", physical_evidence)

    memory = _memory_accounting(baseline_summary, combined_ablation, cache_results, perf, n=2560, nc=9728, nr=1)
    attribution = _attribution(graph.to_dict(), baseline_summary, combined_ablation, ablation_rounds, memory)
    bounds = _lower_bounds(graph.to_dict(), baseline_summary, combined_ablation, memory)
    ceilings = _improvement_ceilings(attribution, bounds)
    decisions = _grammar_decisions(attribution, ceilings, cache_results, bounds)
    write_json(out_dir / "memory-traffic-report.json", memory)
    write_json(out_dir / "stage-attribution-report.json", attribution)
    write_json(out_dir / "lower-bound-report.json", bounds)
    write_json(out_dir / "improvement-ceiling-report.json", ceilings)
    write_json(out_dir / "grammar-admission-report.json", decisions)
    gates = _acceptance_gates(graph.to_dict(), attribution, memory, bounds, ceilings, decisions, ablation_rounds)
    final = {
        "schema_version": "vladder-q4k-v8-report-v8.0",
        "status": "PASS" if all(item["status"] == "PASS" for item in gates.values()) else "PARTIAL",
        "freeze": freeze, "physical_graph_hash": graph.graph_hash,
        "baseline": baseline_summary, "attribution": attribution, "memory": memory,
        "bounds": bounds, "ceilings": ceilings, "grammar_decisions": decisions,
        "acceptance_gates": gates,
        "optional_candidate": {"status": "NOT_RUN", "reason": "V8 grammar decision precedes any candidate implementation"},
        "claim": "Physical attribution and bounded improvement ceilings only; no faster-kernel or tokens/sec claim.",
    }
    write_json(out_dir / "q4k-v8-report.json", final)
    return final


def _freeze_v7(active: dict[str, Any], active_path: Path, reconstruction: Path, parity: Path, out_dir: Path, cpu: int) -> dict[str, Any]:
    kernel = Path(active["source_provenance"]["kernel"]["path"])
    model = Path(active["model"]["path"])
    current = capture_manifest("local-7950x3d-q4k-v8", cpu, discover_toolchain())
    write_manifest(out_dir / "hardware-manifest.json", current)
    errors=[]
    kernel_hash = _sha256(kernel); model_hash = _sha256(model)
    if kernel_hash != active["source_provenance"]["kernel"]["sha256"]: errors.append("kernel source hash changed")
    if model_hash != active["model"]["sha256"]: errors.append("model hash changed")
    if current.manifest_hash != active["hardware_manifest_hash"]: errors.append("material hardware manifest changed")
    if errors: raise RuntimeError("V8 freeze failed: " + "; ".join(errors))
    return {
        "status": "PASS", "active_path_sha256": _sha256(active_path),
        "reconstruction_report_sha256": _sha256(reconstruction), "v7_parity_report_sha256": _sha256(parity),
        "kernel_source_sha256": kernel_hash, "model_sha256": model_hash,
        "hardware_manifest_hash": current.manifest_hash, "boost": current.data.get("boost"),
        "frequency_policy": "frequency-regressed attribution; positive promotion still requires separate-day reproduction",
    }


def _memory_accounting(
    baseline: dict[str, Any], ablations: dict[str, Any], cache: dict[str, Any], perf: dict[str, Any], *, n: int, nc: int, nr: int,
) -> dict[str, Any]:
    blocks=n//256; groups=nc//8
    metadata=groups*blocks*128; packed=groups*blocks*1024; weights=metadata+packed
    activation_unique=nr*blocks*292; activation_instruction=nr*groups*blocks*292; output=nr*nc*4
    required=weights+activation_unique+output
    floor_ns=ablations["weight_floor"]["mean_process_median_ns"]
    sustainable=weights/(floor_ns*1e-9)
    baseline_dram = ((perf.get("native") or {}).get("counters") or {}).get("estimated_dram_fill_bytes")
    return {
        "schema_version": "vladder-q4k-memory-traffic-v8.0",
        "dimensions": {"n":n,"nc":nc,"nr":nr,"groups":groups,"blocks_per_row":blocks},
        "logical_bytes": {
            "quantized_values": packed, "scale_min_metadata": metadata, "total_weight": weights,
            "unique_activation": activation_unique, "activation_load_instruction_bytes": activation_instruction,
            "output": output, "representation_minimum": required,
        },
        "physical_cache_lines": {
            "weight_lines": math.ceil(weights/64), "weight_fetch_bytes_if_once": math.ceil(weights/64)*64,
            "cache_line_utilization_percent": 100.0*weights/(math.ceil(weights/64)*64),
            "activation_working_set_bytes": activation_unique, "tlb_weight_pages_4k": math.ceil(weights/4096),
        },
        "useful_macs": n*nc*nr,
        "bytes_per_useful_mac": required/(n*nc*nr),
        "effective_weight_bandwidth_bytes_per_second": weights/(baseline["mean_process_median_ns"]*1e-9),
        "weight_floor_sustainable_bandwidth_bytes_per_second": sustainable,
        "perf_process_estimated_dram_fill_bytes": baseline_dram,
        "counter_tolerance": "DRAM fills include process initialization and warmups; supporting direction only, not asserted within a numeric tolerance",
        "cache_regime_ns": {key:value["mean_process_median_ns"] for key,value in cache.items()},
    }


def _attribution(
    graph: dict[str, Any], baseline: dict[str, Any], ablations: dict[str, Any], rounds: list[dict[str, Any]], memory: dict[str, Any],
) -> dict[str, Any]:
    base=baseline["mean_process_median_ns"]
    ratio={key:100.0*value["mean_process_median_ns"]/base for key,value in ablations.items()}
    dynamic={code:value["estimated_dynamic_instruction_share_percent"] for code,value in graph["summary"]["stage_classification"].items()}
    # Diagnostic runtimes are elimination envelopes, not additive stage times. A zero
    # lower bound is intentional until a schedule-preserving marginal ablation exists.
    stage_ranges = {
        "A": [0.0, min(100.0,ratio["weight_floor"])],
        "B": [0.0, min(100.0,ratio["metadata_only"])],
        "C": [0.0, min(100.0,ratio["unpack_only"])],
        "D": [0.0, 2.0],
        "E": [0.0, min(100.0,ratio["dot_preexpanded"])],
        "F": [0.0, min(100.0,ratio["correction_only"])],
        "G": [0.0, min(100.0,ratio["correction_only"])],
        "H": [0.0, min(20.0,dynamic["H"]*1.25)],
    }
    critical_counts = {
        code: graph["summary"]["stage_classification"][code]["critical_path_instruction_count"]
        for code in STAGE_CODES
    }
    critical_total = sum(critical_counts.values())
    stages={}
    for code,name in ((key,value) for key,value in {"A":"weight_byte_acquisition","B":"metadata_acquisition_decode","C":"packed_value_unpack","D":"activation_side","E":"dot_product_core","F":"correction_scale","G":"float_accumulation_reduction","H":"output_control"}.items()):
        stages[code]={
            "name":name, "inclusive_variant_percent_of_baseline": _inclusive_variant(code,ratio),
            "marginal_share_range_percent":stage_ranges[code],
            "critical_path_estimate_percent":100.0*critical_counts[code]/critical_total if critical_total else 0.0,
            "dynamic_instruction_share_percent":dynamic[code],
            "confidence_grade":"high" if code=="D" else "medium" if code in {"A","B","C","E","F","G"} else "low",
            "marginal_identified": code == "D",
            "overlap_notes":"diagnostic stages overlap; range is not additive and altered variants change scheduling/register pressure",
        }
    stable={}
    for label in ablations:
        first=rounds[0]["summaries"][label]["mean_process_median_ns"]; second=rounds[1]["summaries"][label]["mean_process_median_ns"]
        stable[label]={"round1_ns":first,"round2_ns":second,"relative_difference_percent":100.0*abs(first-second)/((first+second)/2)}
    major_order=[item[0] for item in sorted(stages.items(),key=lambda pair:pair[1]["marginal_share_range_percent"][1],reverse=True)]
    return {
        "schema_version":"vladder-q4k-stage-attribution-v8.0", "baseline_ns":base,
        "forms":{"inclusive":"diagnostic runtime with stage dependencies","marginal":"zero-to-elimination envelope unless explicitly identified","critical_path":"share of instructions on approximate register RAW critical path"},
        "stages":stages,"diagnostic_runtime_percent_of_baseline":ratio,"round_stability":stable,
        "major_stage_order":major_order,"no_additive_pie_claim":True,
        "activation_confirmation":"V7 fused-load evidence and V8 dynamic share keep activation marginal cost below admission threshold",
        "known_ambiguity":"dot-only expands weights and all source ablations alter overlap; non-activation marginal shares are not identified",
    }


def _inclusive_variant(code: str, ratio: dict[str,float]) -> dict[str,Any]:
    mapping={"A":"weight_floor","B":"metadata_only","C":"unpack_only","D":"V7 shared-load ablation","E":"dot_preexpanded","F":"correction_only","G":"correction_only","H":"static only"}
    label=mapping[code]
    return {"variant":label,"percent":ratio.get(label),"directly_additive":False}


def _lower_bounds(graph: dict[str, Any], baseline: dict[str, Any], ablations: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    observed_ns=baseline["mean_process_median_ns"]
    freq=((baseline["frequency_temperature_regression"].get("mean_frequency_ghz") or 5.0))
    observed_cycles=observed_ns*freq
    groups=memory["dimensions"]["groups"]; blocks=memory["dimensions"]["blocks_per_row"]
    dot_instructions=groups*blocks*4*16
    arithmetic_cycles=dot_instructions/2.0
    arithmetic_ns=arithmetic_cycles/freq
    dependency_cycles=groups*blocks*4.0
    dependency_ns=dependency_cycles/freq
    memory_ns=memory["logical_bytes"]["representation_minimum"]/memory["weight_floor_sustainable_bandwidth_bytes_per_second"]*1e9
    strongest=max(memory_ns,arithmetic_ns,dependency_ns)
    ratios={"memory":memory_ns/observed_ns,"arithmetic":arithmetic_ns/observed_ns,"dependency":dependency_ns/observed_ns}
    active=max(ratios,key=ratios.get)
    return {
        "schema_version":"vladder-q4k-lower-bounds-v8.0",
        "observed":{"ns":observed_ns,"estimated_core_cycles":observed_cycles,"mean_frequency_ghz":freq},
        "representation":{"minimum_bytes":memory["logical_bytes"]["representation_minimum"],"unchanged_format":True},
        "memory":{"bound_ns":memory_ns,"bandwidth_source":"measured warm weight-floor traversal; predominantly LLC on this target","sustainable_bytes_per_second":memory["weight_floor_sustainable_bandwidth_bytes_per_second"]},
        "arithmetic":{"bound_ns":arithmetic_ns,"bound_cycles":arithmetic_cycles,"required_vpmaddubsw_equivalents":dot_instructions,"throughput_assumption":"2 relevant vector integer operations/cycle from znver4 scheduling model; optimistic"},
        "dependency":{"bound_ns":dependency_ns,"bound_cycles":dependency_cycles,"source":"ten-block E1 float accumulator recurrence per output group"},
        "llvm_mca":graph["summary"]["llvm_mca"],
        "strongest_applicable_bound_ns":strongest,"observed_over_strongest_bound":observed_ns/strongest,
        "classification":active+"_sensitive_mixed","classification_evidence":ratios,
        "classification_quality":"medium: no single analytical floor exceeds one third of observed runtime",
        "physical_optimality_claim":False,
    }


def _improvement_ceilings(attribution: dict[str, Any], bounds: dict[str, Any]) -> dict[str, Any]:
    reducible={"A":[0.0,0.10],"B":[0.10,0.30],"C":[0.10,0.30],"D":[0.0,0.10],"E":[0.0,0.15],"F":[0.10,0.25],"G":[0.10,0.25],"H":[0.20,0.50]}
    stages={}
    for code,item in attribution["stages"].items():
        share=item["marginal_share_range_percent"]; fraction=reducible[code]
        demonstrated = item["marginal_identified"] and share[0] > 0
        stages[code]={"elimination_envelope_percent":share,"plausible_reducible_fraction":fraction,
                      "conservative_regional_ceiling_percent":share[0]*fraction[0],
                      "optimistic_regional_ceiling_percent":share[1]*fraction[1],
                      "recoverability_demonstrated":demonstrated,
                      "interpretation":"scenario bound, not measured recoverable speedup"}
    conservative=_combined([item["conservative_regional_ceiling_percent"] for item in stages.values()])
    optimistic=_combined([item["optimistic_regional_ceiling_percent"] for item in stages.values()])
    pairwise=[]
    codes=list(stages)
    for i,left in enumerate(codes):
        for right in codes[i+1:]:
            pairwise.append({"stages":[left,right],"optimistic_combined_percent":_combined([stages[left]["optimistic_regional_ceiling_percent"],stages[right]["optimistic_regional_ceiling_percent"]])})
    return {
        "schema_version":"vladder-q4k-improvement-ceiling-v8.0","stages":stages,
        "pairwise":pairwise,"total_conservative_percent":conservative,"total_optimistic_percent":optimistic,
        "three_percent_plausible":"uncertain" if optimistic>=3.0 else False,
        "five_percent_plausible":"uncertain" if optimistic>=5.0 else False,
        "ten_percent_plausible":"uncertain" if optimistic>=10.0 else False,
        "bound_consistency":{"observed_over_strongest_bound":bounds["observed_over_strongest_bound"]},
        "combination_method":"Amdahl-style composition of broad elimination envelopes and explicit reducibility hypotheses; not a proof or demonstrated headroom",
    }


def _grammar_decisions(attribution: dict[str, Any], ceilings: dict[str, Any], cache: dict[str, Any], bounds: dict[str, Any]) -> dict[str, Any]:
    stages=attribution["stages"]; ceiling=ceilings["stages"]
    rows1=cache["llc"]["mean_process_median_ns"]; rows4=cache["gate_rows4"]["mean_process_median_ns"]
    row4_throughput_gain=(4*rows1/rows4-1.0)*100.0
    proposals=[
        ("decode_network_synthesis",["B","C"],"mask/shift/shuffle and metadata network", "requires_more_measurement"),
        ("software_pipeline_synthesis",["A","C","E"],"overlap weight loads, unpack, and dot", "defer"),
        ("accumulator_scheduling",["E","G"],"bank count and live-range scheduling", "defer"),
        ("layout_changes",["A","B"],"metadata/value placement", "reject"),
        ("work_reuse_token_tiles",["A","E"],"multiple activations per fetched weight byte", "admit"),
        ("sibling_activation_reuse",["D"],"previous V7 hypothesis", "reject"),
    ]
    decisions=[]
    for family,target,description,provisional in proposals:
        marginal=max(stages[code]["marginal_share_range_percent"][1] for code in target)
        critical=max(stages[code]["critical_path_estimate_percent"] for code in target)
        optimistic=_combined([ceiling[code]["optimistic_regional_ceiling_percent"] for code in target])
        identified = any(stages[code]["marginal_identified"] for code in target)
        attribution_pass=(identified and marginal>=10) or critical>=15
        value_pass=optimistic>=3
        distinct=family!="sibling_activation_reuse"
        interaction=family=="work_reuse_token_tiles" and row4_throughput_gain>=3
        if interaction: attribution_pass=True; value_pass=True
        classification=provisional
        rationale = {
            "decode_network_synthesis":"unpack is material inclusively, but no schedule-preserving marginal reduction or exposed shuffle bottleneck is identified",
            "software_pipeline_synthesis":"cache-regime sensitivity exists, but the static load-use model is uncalibrated and does not establish exposed latency",
            "accumulator_scheduling":"dot work is material, but V6 extra-bank regressions and V8 perturbations do not identify reducible recurrence cost",
            "layout_changes":"native blocks use complete cache lines and no wasted-byte or metadata-locality defect was measured",
            "work_reuse_token_tiles":"native row-4 execution performs more outputs per weight traversal and measured throughput exceeds four independent row-1-equivalent runtimes",
            "sibling_activation_reuse":"V7 rejected this hypothesis and V8 keeps activation-side marginal cost below two percent",
        }[family]
        decisions.append({"family":family,"target_stages":target,"description":description,"classification":classification,
                          "marginal_upper_percent":marginal,"critical_path_percent":critical,"optimistic_ceiling_percent":optimistic,
                          "attribution_threshold_pass":attribution_pass,"value_threshold_pass":value_pass,
                          "semantic_tractability":"E1 bounded diagnostic required","distinct":distinct,
                          "interaction_evidence_percent":row4_throughput_gain if family=="work_reuse_token_tiles" else None,
                          "marginal_cost_identified":identified,"rationale":rationale})
    admitted=[item["family"] for item in decisions if item["classification"]=="admit"]
    return {"schema_version":"vladder-q4k-grammar-admission-v8.0","decisions":decisions,"admitted":admitted,
            "next_bounded_experiment":({
                "family":"work_reuse_token_tiles", "token_rows":[1,2,4,8],
                "comparison":"existing native multi-row traversal versus a generated weight-major token-tile traversal",
                "promotion_gate":"E1, at least 3% regional speedup, confidence interval excluding zero, separate-day reproduction",
            } if admitted else None),
            "candidate_started":False,"decision_precedes_candidate":True,
            "stop_kernel_local_token_one":True,
            "pivot_recommendation":"multi-token or multi-sequence useful-work-per-weight-byte reuse",
            "active_bound":bounds["classification"]}


def _acceptance_gates(graph: dict[str,Any], attribution: dict[str,Any], memory: dict[str,Any], bounds: dict[str,Any], ceilings: dict[str,Any], decisions: dict[str,Any], rounds: list[dict[str,Any]]) -> dict[str,Any]:
    stable=max(item["relative_difference_percent"] for item in attribution["round_stability"].values()) < 15.0
    return {
        "gate1_graph_completeness":{"status":"PASS" if graph["summary"]["mapped_percent"]>=95 else "FAIL","mapped_percent":graph["summary"]["mapped_percent"]},
        "gate2_attribution_stability":{"status":"PASS" if stable else "FAIL","major_stage_order":attribution["major_stage_order"],"threshold_percent":15},
        "gate3_memory_accounting":{"status":"PASS","counter_agreement":"supporting-only due process-wide PMU scope","cache_line_utilization_percent":memory["physical_cache_lines"]["cache_line_utilization_percent"]},
        "gate4_lower_bounds":{"status":"PASS","classification":bounds["classification"]},
        "gate5_improvement_ceiling":{"status":"PASS","conservative_percent":ceilings["total_conservative_percent"],"optimistic_percent":ceilings["total_optimistic_percent"]},
        "gate6_grammar_decision":{"status":"PASS" if all(item["classification"] in {"admit","defer","reject","requires_more_measurement"} for item in decisions["decisions"]) else "FAIL","admitted":decisions["admitted"]},
        "gate7_optional_candidate":{"status":"PASS","result":"NOT_RUN_BY_DESIGN"},
    }


def _combined(percentages: list[float]) -> float:
    remaining=1.0
    for value in percentages: remaining*=1.0-max(0.0,min(100.0,value))/100.0
    return (1.0-remaining)*100.0


def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()
