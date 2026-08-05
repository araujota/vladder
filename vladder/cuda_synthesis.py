from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable

import yaml

from z3 import Int, Or, Solver, sat

from .cuda_runtime import (
    collect_ncu_counters,
    compile_cuda_source,
    inspect_cuda_module,
    write_cuda_artifact,
)
from .gpu_ir import (
    GPUArchitecture,
    GPUExecutionPlan,
    capture_gpu_kernel,
    estimate_gpu_cost,
)
from .gpu_physical import rank_gpu_candidates
from .language_adapter import canonical_hash, file_sha256


CUDA_POINTWISE_GRAMMAR_VERSION = "cuda-pointwise-schedule-v1"


@dataclass(frozen=True)
class CUDAPointwiseRegion:
    source: str
    entry_point: str
    destination: str
    source_view: str
    extent: str
    index: str
    index_type: str
    expression: str
    function_start: int
    body_start: int
    body_end: int
    source_hash: str
    expression_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matching_brace(source: str, opening: int) -> int:
    depth = 0
    for offset in range(opening, len(source)):
        character = source[offset]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return offset
    raise ValueError("CUDA kernel body has no matching closing brace")


def extract_cuda_pointwise_region(source_path: Path, entry_point: str) -> CUDAPointwiseRegion:
    source_path = source_path.resolve()
    source = source_path.read_text()
    function_pattern = re.compile(
        rf"(?P<header>(?:extern\s+\"C\"\s+)?(?:(?:__global__|__launch_bounds__\s*\([^)]*\)|inline|static)\s+)*void\s+{re.escape(entry_point)}\s*\((?P<params>[^)]*)\)\s*)\{{",
        re.MULTILINE,
    )
    match = function_pattern.search(source)
    if not match or "__global__" not in match.group("header"):
        raise ValueError(f"bounded CUDA kernel {entry_point!r} was not found")
    body_start = match.end() - 1
    body_end = _matching_brace(source, body_start)
    body = source[body_start + 1:body_end]
    parameters = match.group("params")
    destination_match = re.search(r"(?<!const\s)\bfloat\s*\*\s*(\w+)", parameters)
    source_match = re.search(r"\bconst\s+float\s*\*\s*(\w+)", parameters)
    extent_match = re.search(r"\b((?:std::)?size_t)\s+(\w+)", parameters)
    if not destination_match or not source_match or not extent_match:
        raise ValueError("CUDA pointwise-v1 requires float*, const float*, and size_t parameters")
    destination = destination_match.group(1)
    source_view = source_match.group(1)
    index_declaration = re.search(
        r"\b(?:const\s+)?((?:std::)?size_t)\s+(\w+)\s*=\s*([^;]+);",
        body,
    )
    if not index_declaration:
        raise ValueError("CUDA pointwise-v1 requires one explicit size_t global index")
    index_type, index, index_expression = index_declaration.groups()
    if not all(token in index_expression for token in ("blockIdx.x", "blockDim.x", "threadIdx.x")):
        raise ValueError("CUDA pointwise-v1 index must be blockIdx.x * blockDim.x + threadIdx.x")
    assignment_pattern = re.compile(
        rf"\b{re.escape(destination)}\s*\[\s*{re.escape(index)}\s*\]\s*=\s*(?P<expression>[^;]+);"
    )
    assignments = list(assignment_pattern.finditer(body))
    if len(assignments) != 1:
        raise ValueError("CUDA pointwise-v1 requires exactly one destination assignment")
    expression = " ".join(assignments[0].group("expression").split())
    extent = extent_match.group(2)
    if not re.search(rf"\bif\s*\(\s*{re.escape(index)}\s*<\s*{re.escape(extent)}\s*\)", body):
        raise ValueError("CUDA pointwise-v1 requires an index < extent guard")
    forbidden = ("for", "while", "do", "__syncthreads", "atomic", "__shared__", "asm")
    if any(re.search(rf"\b{re.escape(token)}\b", body) for token in forbidden):
        raise ValueError("CUDA pointwise-v1 baseline must be a single lane-independent guarded assignment")
    if body.count("if") != 1:
        raise ValueError("CUDA pointwise-v1 permits exactly one bounds branch")
    expression_without_load = re.sub(
        rf"\b{re.escape(source_view)}\s*\[\s*{re.escape(index)}\s*\]",
        "VALUE",
        expression,
    )
    identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", expression_without_load))
    if identifiers - {"VALUE", "f", "F"}:
        raise ValueError(f"CUDA pointwise-v1 expression has unsupported identifiers: {sorted(identifiers)}")
    if not re.fullmatch(r"[A-Za-z0-9_+\-*/().\s]+", expression_without_load):
        raise ValueError("CUDA pointwise-v1 expression contains unsupported syntax")
    return CUDAPointwiseRegion(
        str(source_path), entry_point, destination, source_view, extent, index, index_type,
        expression, match.start(), body_start, body_end, file_sha256(source_path),
        hashlib.sha256(expression.encode("utf-8")).hexdigest(),
    )


def render_cuda_schedule(region: CUDAPointwiseRegion, elements_per_thread: int) -> str:
    if elements_per_thread not in {1, 2, 4, 8, 16}:
        raise ValueError("CUDA pointwise-v1 supports unroll factors 1,2,4,8,16")
    source = Path(region.source).read_text()
    if elements_per_thread == 1:
        body = f"{{\n    const {region.index_type} {region.index} = static_cast<{region.index_type}>(blockIdx.x) * blockDim.x + threadIdx.x;\n    if ({region.index} < {region.extent}) {{\n        {region.destination}[{region.index}] = {region.expression};\n    }}\n}}"
    else:
        body = (
            "{\n"
            f"    const {region.index_type} vladder_base = static_cast<{region.index_type}>(blockIdx.x) * blockDim.x * {elements_per_thread} + threadIdx.x;\n"
            "#pragma unroll\n"
            f"    for (unsigned int vladder_lane = 0; vladder_lane < {elements_per_thread}; ++vladder_lane) {{\n"
            f"        const {region.index_type} {region.index} = vladder_base + static_cast<{region.index_type}>(vladder_lane) * blockDim.x;\n"
            f"        if ({region.index} < {region.extent}) {{\n"
            f"            {region.destination}[{region.index}] = {region.expression};\n"
            "        }\n"
            "    }\n"
            "}"
        )
    return source[:region.body_start] + body + source[region.body_end + 1:]


def prove_cuda_schedule(
    region: CUDAPointwiseRegion,
    *,
    threads: int,
    elements_per_thread: int,
    logical_extent: int,
    candidate_source: Path,
    output_directory: Path,
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    obligations: list[dict[str, Any]] = []
    smt: list[str] = []

    def record(identifier: str, solver: Solver, detail: dict[str, Any]) -> None:
        result = solver.check()
        obligations.append({
            "id": identifier,
            "status": "PASS" if result != sat else "FAIL",
            "solver_result": str(result).upper(),
            "detail": detail,
            "counterexample": str(solver.model()) if result == sat else None,
        })
        smt.append(solver.to_smt2())

    tile = threads * elements_per_thread
    maximum_size_t = (1 << 64) - 1
    maximum_safe_extent = min(maximum_size_t - (tile - 1), (1 << 63) - 1)
    if logical_extent <= 0 or logical_extent > maximum_safe_extent:
        raise ValueError("logical extent is outside the proved non-wrapping CUDA schedule envelope")
    extent = Int("extent")
    index = Int("index")
    block = index / tile
    lane_linear = index % tile
    thread = lane_linear % threads
    lane = lane_linear / threads
    reconstructed = block * tile + lane * threads + thread
    launched_blocks = (extent + tile - 1) / tile
    coverage = Solver()
    coverage.add(extent > 0, extent <= maximum_safe_extent, index >= 0, index < extent)
    coverage.add(Or(
        reconstructed != index,
        block >= launched_blocks,
        thread < 0,
        thread >= threads,
        lane < 0,
        lane >= elements_per_thread,
    ))
    record("cuda.schedule.coverage", coverage, {
        "threads": threads,
        "elements_per_thread": elements_per_thread,
        "physical_test_extent": logical_extent,
        "parametric_extent": f"1 <= extent <= {maximum_safe_extent}",
    })

    block_a, block_b = Int("block_a"), Int("block_b")
    thread_a, thread_b = Int("thread_a"), Int("thread_b")
    lane_a, lane_b = Int("lane_a"), Int("lane_b")
    value_a = block_a * tile + lane_a * threads + thread_a
    value_b = block_b * tile + lane_b * threads + thread_b
    injective = Solver()
    injective.add(block_a >= 0, block_b >= 0)
    injective.add(thread_a >= 0, thread_a < threads, thread_b >= 0, thread_b < threads)
    injective.add(lane_a >= 0, lane_a < elements_per_thread, lane_b >= 0, lane_b < elements_per_thread)
    injective.add(value_a == value_b)
    injective.add(Or(block_a != block_b, thread_a != thread_b, lane_a != lane_b))
    record("cuda.schedule.injective", injective, {
        "mapping": "block * threads * elements_per_thread + lane * threads + thread",
    })

    last_block = launched_blocks - 1
    maximum_generated_index = last_block * tile + tile - 1
    no_wrap = Solver()
    no_wrap.add(extent > 0, extent <= maximum_safe_extent)
    no_wrap.add(maximum_generated_index > maximum_size_t)
    record("cuda.schedule.size_t_no_wrap", no_wrap, {
        "size_t_bits": 64,
        "tile": tile,
        "maximum_safe_extent": maximum_safe_extent,
    })

    candidate_text = candidate_source.read_text()
    candidate_assignments = re.findall(
        rf"\b{re.escape(region.destination)}\s*\[\s*{re.escape(region.index)}\s*\]\s*=\s*([^;]+);",
        candidate_text,
    )
    candidate_expression = " ".join(candidate_assignments[0].split()) if len(candidate_assignments) == 1 else ""
    candidate_expression_hash = hashlib.sha256(candidate_expression.encode("utf-8")).hexdigest()
    expression_equal = len(candidate_assignments) == 1 and candidate_expression_hash == region.expression_hash
    expression_solver = Solver()
    expression_solver.add(not expression_equal)
    record("cuda.expression.literal_identity", expression_solver, {
        "baseline_expression_hash": region.expression_hash,
        "candidate_expression_hash": candidate_expression_hash,
        "method": "source-normalized literal expression identity",
    })
    smt_path = output_directory / "cuda-schedule.smt2"
    smt_path.write_text("\n; ---- obligation ----\n".join(smt))
    passed = all(item["status"] == "PASS" for item in obligations)
    report = {
        "schema_version": "vladder-cuda-schedule-proof-v1",
        "status": "PASS" if passed else "FAIL",
        "grammar_version": CUDA_POINTWISE_GRAMMAR_VERSION,
        "region": region.to_dict(),
        "candidate_source": str(candidate_source),
        "candidate_source_hash": file_sha256(candidate_source),
        "obligations": obligations,
        "artifact": str(smt_path),
        "proof_scope": (
            "lane-independent pointwise expression identity and parametric exact mixed-radix "
            "index partition under the declared 64-bit non-wrapping launch envelope"
        ),
        "excluded_claims": [
            "CUDA compiler correctness",
            "driver and final machine scheduling",
            "host queue and external protocols",
            "kernels outside cuda-pointwise-schedule-v1",
        ],
    }
    (output_directory / "cuda-schedule-proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def synthesize_cuda_pointwise(
    source: Path,
    entry_point: str,
    architecture: GPUArchitecture,
    output_directory: Path,
    *,
    logical_extent: int,
    thread_sizes: Iterable[int] = (64, 128, 256, 512),
    unroll_factors: Iterable[int] = (1, 2, 4, 8),
    baseline_threads: int = 256,
    warmup: int = 10,
    iterations: int = 100,
    static_finalists: int = 8,
) -> dict[str, Any]:
    source = source.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    region = extract_cuda_pointwise_region(source, entry_point)
    baseline_directory = output_directory / "baseline"
    baseline_module = baseline_directory / "baseline.ptx"
    baseline_compilation = compile_cuda_source(
        source, baseline_module, architecture=architecture.architecture
    )
    baseline_resources = inspect_cuda_module(baseline_module, entry_point=entry_point)
    baseline_artifact_path = baseline_directory / "artifact.json"
    baseline_artifact = write_cuda_artifact(
        baseline_artifact_path,
        module=baseline_module,
        entry_point=entry_point,
        logical_extent=logical_extent,
        threads=baseline_threads,
        elements_per_thread=1,
        warmup=warmup,
        iterations=iterations,
        provenance={"kind": "production-source-baseline", **baseline_compilation},
    )
    rows: list[dict[str, Any]] = []
    for unroll in sorted(set(int(value) for value in unroll_factors)):
        source_directory = output_directory / f"source-u{unroll}"
        source_directory.mkdir(parents=True, exist_ok=True)
        candidate_source = source_directory / f"{entry_point}-u{unroll}.cu"
        candidate_source.write_text(render_cuda_schedule(region, unroll))
        module = source_directory / f"{entry_point}-u{unroll}.ptx"
        compilation = compile_cuda_source(
            candidate_source, module, architecture=architecture.architecture
        )
        module_resources = inspect_cuda_module(module, entry_point=entry_point)
        capture = capture_gpu_kernel(module, source_directory / "capture", entry_point=entry_point)
        capture = replace(capture, resources=replace(
            capture.resources,
            registers_per_thread=int(module_resources["registers_per_thread"]),
            static_shared_bytes=int(module_resources["static_shared_bytes"]),
            local_bytes_per_thread=int(module_resources["local_bytes_per_thread"]),
        ))
        for threads in sorted(set(int(value) for value in thread_sizes)):
            if threads <= 0 or threads > architecture.max_threads_per_block:
                continue
            candidate_id = f"cuda-t{threads}-u{unroll}"
            candidate_directory = output_directory / "candidates" / candidate_id
            candidate_directory.mkdir(parents=True, exist_ok=True)
            proof = prove_cuda_schedule(
                region,
                threads=threads,
                elements_per_thread=unroll,
                logical_extent=logical_extent,
                candidate_source=candidate_source,
                output_directory=candidate_directory / "proof",
            )
            artifact_path = candidate_directory / "artifact.json"
            artifact = write_cuda_artifact(
                artifact_path,
                module=module,
                entry_point=entry_point,
                logical_extent=logical_extent,
                threads=threads,
                elements_per_thread=unroll,
                warmup=warmup,
                iterations=iterations,
                provenance={
                    "candidate_id": candidate_id,
                    "grammar_version": CUDA_POINTWISE_GRAMMAR_VERSION,
                    "derivation": [f"schedule:threads-{threads}", f"schedule:contiguous-unroll-{unroll}"],
                    "source": str(candidate_source),
                    "proof": proof,
                    "compilation": compilation,
                },
            )
            plan = GPUExecutionPlan(
                candidate_id,
                (threads, 1, 1),
                1,
                1,
                "direct-global",
                "baseline-scope",
                0,
                "source_rewrite",
                ("cuda-pointwise-schedule-v1 recognized", "bounds guard preserved", "expression literal identity"),
                (f"schedule:threads-{threads}", f"schedule:contiguous-unroll-{unroll}"),
            )
            cost = estimate_gpu_cost(capture, architecture, plan)
            rows.append({
                "id": candidate_id,
                "threads": threads,
                "elements_per_thread": unroll,
                "source": str(candidate_source),
                "source_hash": file_sha256(candidate_source),
                "module": str(module),
                "module_hash": file_sha256(module),
                "module_resources": module_resources,
                "proof": proof,
                "artifact": str(artifact_path),
                "artifact_hash": artifact["artifact_hash"],
                "plan": plan.to_dict(),
                "cost": cost.to_dict(),
                "semantic_status": "PASS" if proof["status"] == "PASS" else "FAIL",
            })
    rows.sort(key=lambda item: (
        item["semantic_status"] != "PASS",
        not item["cost"]["feasible"],
        item["cost"]["static_score"],
        item["id"],
    ))
    finalists = [item for item in rows if item["semantic_status"] == "PASS" and item["cost"]["feasible"]][:static_finalists]
    report = {
        "schema_version": "vladder-cuda-pointwise-synthesis-v1",
        "status": "PASS" if finalists else "NO_EXECUTABLE_CANDIDATE",
        "grammar_version": CUDA_POINTWISE_GRAMMAR_VERSION,
        "source": str(source),
        "source_hash": file_sha256(source),
        "region": region.to_dict(),
        "architecture": architecture.to_dict(),
        "baseline": {
            "id": "baseline",
            "source": str(source),
            "module": str(baseline_module),
            "module_hash": file_sha256(baseline_module),
            "module_resources": baseline_resources,
            "artifact": str(baseline_artifact_path),
            "artifact_hash": baseline_artifact["artifact_hash"],
        },
        "candidates": rows,
        "static_finalists": finalists,
        "search_coverage": {
            "thread_sizes": sorted(set(int(value) for value in thread_sizes)),
            "unroll_factors": sorted(set(int(value) for value in unroll_factors)),
            "enumerated": len(rows),
            "physically_selected": len(finalists),
            "classification": "bounded_exhaustive_schedule_region",
        },
        "promotion": {"promotable": False, "reason": "physical exact-output ranking has not run"},
    }
    (output_directory / "cuda-synthesis.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def emit_cuda_replacement(
    synthesis: dict[str, Any],
    winner_id: str,
    output_directory: Path,
) -> dict[str, Any]:
    candidates = {item["id"]: item for item in synthesis.get("candidates", [])}
    if winner_id not in candidates:
        raise ValueError(f"CUDA winner {winner_id!r} is not in synthesis")
    candidate = candidates[winner_id]
    if candidate.get("semantic_status") != "PASS" or candidate.get("proof", {}).get("status") != "PASS":
        raise ValueError("CUDA replacement requires a passing schedule proof")
    baseline_path = Path(synthesis["source"])
    candidate_path = Path(candidate["source"])
    baseline = baseline_path.read_text().splitlines(keepends=True)
    selected = candidate_path.read_text().splitlines(keepends=True)
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    optimized = output_directory / "optimized.cu"
    patch = output_directory / "optimized.patch"
    optimized.write_text("".join(selected))
    patch.write_text("".join(difflib.unified_diff(
        baseline,
        selected,
        fromfile=str(baseline_path),
        tofile=str(baseline_path),
    )))
    report = {
        "schema_version": "vladder-cuda-replacement-v1",
        "winner_id": winner_id,
        "baseline_source_hash": synthesis["source_hash"],
        "optimized_source_hash": file_sha256(optimized),
        "candidate_source_hash": candidate["source_hash"],
        "proof_hash": canonical_hash(candidate["proof"]),
        "artifacts": {"optimized_source": str(optimized), "patch": str(patch)},
        "claim_boundary": "bounded CUDA pointwise kernel source; host launch integration must use the selected threads/elements-per-thread plan",
    }
    (output_directory / "replacement.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def optimize_cuda_pointwise(
    source: Path,
    entry_point: str,
    architecture: GPUArchitecture,
    output_directory: Path,
    *,
    logical_extent: int,
    thread_sizes: Iterable[int] = (64, 128, 256, 512),
    unroll_factors: Iterable[int] = (1, 2, 4, 8),
    baseline_threads: int = 256,
    warmup: int = 10,
    iterations: int = 100,
    static_finalists: int = 8,
    processes: int = 10,
    minimum_effect_percent: float = 1.0,
    bootstrap_rounds: int = 2000,
    seed: int = 0,
    collect_counters: bool = True,
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    synthesis = synthesize_cuda_pointwise(
        source,
        entry_point,
        architecture,
        output_directory / "synthesis",
        logical_extent=logical_extent,
        thread_sizes=thread_sizes,
        unroll_factors=unroll_factors,
        baseline_threads=baseline_threads,
        warmup=warmup,
        iterations=iterations,
        static_finalists=static_finalists,
    )
    counter_report: dict[str, Any] = {
        "status": "not_requested" if not collect_counters else "tool_unavailable",
        "collector": shutil.which("ncu"),
        "baseline": None,
        "candidates": {},
        "errors": [],
    }
    baseline_counter_path: Path | None = None
    candidate_counter_paths: dict[str, Path] = {}
    if collect_counters and shutil.which("ncu"):
        counter_report["status"] = "pass"
        baseline_counter_path = output_directory / "counters" / "baseline.yaml"
        try:
            counter_report["baseline"] = collect_ncu_counters(
                Path(synthesis["baseline"]["artifact"]), baseline_counter_path
            )
        except Exception as error:
            baseline_counter_path = None
            counter_report["status"] = "partial"
            counter_report["errors"].append({"id": "baseline", "error": str(error)})
        for candidate in synthesis["static_finalists"]:
            counter_path = output_directory / "counters" / f"{candidate['id']}.yaml"
            try:
                counter_report["candidates"][candidate["id"]] = collect_ncu_counters(
                    Path(candidate["artifact"]), counter_path
                )
                candidate_counter_paths[candidate["id"]] = counter_path
            except Exception as error:
                counter_report["status"] = "partial"
                counter_report["errors"].append({"id": candidate["id"], "error": str(error)})

    ranking_manifest = {
        "schema_version": "gpu-physical-ranking-v1",
        "hardware_identity": architecture.device_uuid,
        "contract": {"exact_observables": True},
        "baseline": {
            "id": "baseline",
            "artifact": synthesis["baseline"]["artifact"],
            **({"counter_evidence": str(baseline_counter_path)} if baseline_counter_path else {}),
        },
        "candidates": [
            {
                "id": candidate["id"],
                "artifact": candidate["artifact"],
                **(
                    {"counter_evidence": str(candidate_counter_paths[candidate["id"]])}
                    if candidate["id"] in candidate_counter_paths else {}
                ),
            }
            for candidate in synthesis["static_finalists"]
        ],
        "runner": {
            "builtin": "cuda-artifact-v1",
            "evidence_class": "hardware-device-timestamp",
            "processes": processes,
            "minimum_effect_percent": minimum_effect_percent,
            "bootstrap_rounds": bootstrap_rounds,
            "seed": seed,
            "timeout_seconds": 180,
        },
    }
    ranking_path = output_directory / "ranking-manifest.yaml"
    ranking_path.write_text(yaml.safe_dump(ranking_manifest, sort_keys=False))
    ranking = rank_gpu_candidates(ranking_path, output_directory / "ranking")
    replacement = None
    winner = ranking.get("winner")
    if winner and winner.get("promotable"):
        replacement = emit_cuda_replacement(
            synthesis,
            str(winner["candidate_id"]),
            output_directory / "replacement",
        )
        candidate = next(
            item for item in synthesis["candidates"]
            if item["id"] == winner["candidate_id"]
        )
        launch_plan = {
            "schema_version": "vladder-cuda-launch-plan-v1",
            "entry_point": entry_point,
            "threads": candidate["threads"],
            "elements_per_thread": candidate["elements_per_thread"],
            "blocks_expression": (
                "logical_extent / (threads * elements_per_thread) + "
                "(logical_extent % (threads * elements_per_thread) != 0)"
            ),
            "preconditions": {
                "logical_extent_min": 1,
                "logical_extent_max_no_wrap": min(
                    (1 << 64) - 1 - (candidate["threads"] * candidate["elements_per_thread"] - 1),
                    (1 << 63) - 1,
                ),
                "blocks_max": architecture.max_grid_dim_x,
                "guard": "computed blocks <= blocks_max",
            },
            "candidate_id": candidate["id"],
            "candidate_plan_hash": candidate["plan"]["graph_hash"],
        }
        launch_path = output_directory / "replacement" / "launch-plan.json"
        launch_path.write_text(json.dumps(launch_plan, indent=2, sort_keys=True) + "\n")
        replacement["artifacts"]["launch_plan"] = str(launch_path)
        (output_directory / "replacement" / "replacement.json").write_text(
            json.dumps(replacement, indent=2, sort_keys=True) + "\n"
        )
    report = {
        "schema_version": "vladder-cuda-pointwise-optimization-v1",
        "status": "PASS",
        "grammar_version": CUDA_POINTWISE_GRAMMAR_VERSION,
        "synthesis": synthesis,
        "ranking": ranking,
        "counter_collection": counter_report,
        "replacement": replacement,
        "promotion": ranking["promotion"],
        "bounded_classification": "bounded_optimal_local" if ranking["promotion"]["promotable"] else "no_verified_physical_win",
        "claim_boundary": "bounded pointwise CUDA kernel and selected launch plan; host protocol integration remains separate",
    }
    (output_directory / "cuda-optimization.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
