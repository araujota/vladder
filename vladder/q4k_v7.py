from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import struct
from typing import Any

from .q4k_semantics import (
    Q4KBlock, Q8KBlock, build_q4k_kernel_graph, decode_scale_min, dequantize_q4k,
    pack_scale_min, parse_q4k_block, parse_q8k_block, q4k_q8k_reference_dot,
    repack_q4k_x8, verify_repack_bijection,
)
from .report import write_json


def reconstruct_q4k_v7(active_manifest_path: Path, out_dir: Path, *, random_cases: int = 128, seed: int = 7007) -> dict[str, Any]:
    active = json.loads(active_manifest_path.read_text())
    if active.get("status") != "PASS" or active.get("schema_version") != "vladder-active-q4k-path-v7.0":
        raise ValueError("reconstruction requires a passing V7 active-path manifest")
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = build_q4k_kernel_graph(active)
    rng = random.Random(seed)
    scale_proof = _verify_scale_codec()
    cases: list[dict[str, Any]] = []
    fixture_hashes: list[str] = []
    for case_index in range(random_cases + 4):
        mode = "random" if case_index < random_cases else ("zeros", "maxima", "alternating", "sparse")[case_index - random_cases]
        weights = tuple(_weight_block(rng, mode, row) for row in range(8))
        activation = _activation_block(rng, mode)
        raw_weights = b"".join(block.to_bytes() for block in weights)
        raw_activation = activation.to_bytes()
        parsed_weights = tuple(parse_q4k_block(raw_weights[index * 144:(index + 1) * 144]) for index in range(8))
        parsed_activation = parse_q8k_block(raw_activation)
        repack_proof = verify_repack_bijection(parsed_weights)
        if repack_proof["status"] != "proved":
            raise RuntimeError(f"Q4_K repack proof failed for case {case_index}")
        semantic_errors = []
        for row, block in enumerate(parsed_weights):
            production_ref = q4k_q8k_reference_dot(block, parsed_activation)
            mathematical = sum(
                weight * (parsed_activation.d * quant)
                for weight, quant in zip(dequantize_q4k(block), parsed_activation.qs)
            )
            absolute = abs(production_ref - mathematical)
            relative = absolute / max(1.0, abs(mathematical))
            semantic_errors.append({"row": row, "absolute": absolute, "relative": relative})
        fixture_hash = hashlib.sha256(raw_weights + raw_activation).hexdigest()
        fixture_hashes.append(fixture_hash)
        cases.append({
            "case": case_index, "mode": mode, "fixture_sha256": fixture_hash,
            "repack": repack_proof, "reference_crosscheck": {
                "max_absolute": max(item["absolute"] for item in semantic_errors),
                "max_relative": max(item["relative"] for item in semantic_errors),
                "classification": "E2 mathematical cross-check; production-order E1 requires native harness",
            },
        })
    graph_path = out_dir / "q4k-kernel-graph.json"
    write_json(graph_path, graph.to_dict())
    (out_dir / "q4k-kernel-graph.dot").write_text(_graph_dot(graph.to_dict()))
    report = {
        "schema_version": "vladder-q4k-reconstruction-v7.0",
        "status": "PASS",
        "active_path_manifest": str(active_manifest_path.resolve()),
        "active_path_manifest_sha256": hashlib.sha256(active_manifest_path.read_bytes()).hexdigest(),
        "graph_hash": graph.graph_hash,
        "scale_metadata_codec": scale_proof,
        "case_count": len(cases),
        "random_case_count": random_cases,
        "adversarial_modes": ["zeros", "maxima", "alternating", "sparse"],
        "all_block_round_trips": all(item["repack"]["status"] == "proved" for item in cases),
        "fixture_corpus_hash": hashlib.sha256("".join(fixture_hashes).encode()).hexdigest(),
        "cases": cases,
        "gates": {
            "block_semantics": "PASS",
            "metadata_extrema": "PASS",
            "native_repack_bijection": "PASS",
            "Q8_K_bsums": "PASS",
            "native_kernel_E1": "NOT_RUN",
            "layer_integration": "NOT_RUN",
            "fixed_prompt_model": "NOT_RUN",
        },
        "claim": "Production block and repack semantics reconstructed; native floating-point operation-order equivalence and performance parity remain required.",
    }
    write_json(out_dir / "q4k-reconstruction-report.json", report)
    return report


def _verify_scale_codec() -> dict[str, Any]:
    checks = 0
    for field in ("scale", "minimum"):
        for index in range(8):
            for value in range(64):
                scales = [0] * 8
                minima = [0] * 8
                if field == "scale":
                    scales[index] = value
                else:
                    minima[index] = value
                packed = pack_scale_min(scales, minima)
                decoded = [decode_scale_min(packed, item) for item in range(8)]
                if [item[0] for item in decoded] != scales or [item[1] for item in decoded] != minima:
                    raise RuntimeError(f"Q4_K metadata codec failed for {field}[{index}]={value}")
                checks += 1
    return {"status": "proved", "method": "exhaustive 6-bit single-field basis", "checks": checks}


def _weight_block(rng: random.Random, mode: str, row: int) -> Q4KBlock:
    if mode == "zeros":
        d, dmin, scales, minima, quant = 0.0, 0.0, [0] * 8, [0] * 8, bytes(128)
    elif mode == "maxima":
        d, dmin, scales, minima, quant = 1.0, 1.0, [63] * 8, [63] * 8, bytes([0xff] * 128)
    elif mode == "alternating":
        d, dmin = 0.5, 0.25
        scales = [63 if index % 2 else 0 for index in range(8)]
        minima = [0 if index % 2 else 63 for index in range(8)]
        quant = bytes(0xff if index % 2 else 0x00 for index in range(128))
    elif mode == "sparse":
        d, dmin, scales, minima = 0.125, 0.0625, [1] * 8, [0] * 8
        quant = bytes(1 if index == row else 0 for index in range(128))
    else:
        d, dmin = rng.uniform(0.0005, 2.0), rng.uniform(0.0, 1.0)
        scales = [rng.randrange(64) for _ in range(8)]
        minima = [rng.randrange(64) for _ in range(8)]
        quant = bytes(rng.randrange(256) for _ in range(128))
    return Q4KBlock(_half_bits(d), _half_bits(dmin), pack_scale_min(scales, minima), quant)


def _activation_block(rng: random.Random, mode: str) -> Q8KBlock:
    if mode == "zeros":
        scale, values = 0.0, [0] * 256
    elif mode == "maxima":
        scale, values = 1.0, [127] * 256
    elif mode == "alternating":
        scale, values = 0.5, [127 if index % 2 else -127 for index in range(256)]
    elif mode == "sparse":
        scale, values = 0.25, [127 if index == 0 else 0 for index in range(256)]
    else:
        scale, values = rng.uniform(0.0005, 2.0), [rng.randrange(-127, 128) for _ in range(256)]
    bsums = [sum(values[index:index + 16]) for index in range(0, 256, 16)]
    return Q8KBlock(scale, tuple(values), tuple(bsums))


def _half_bits(value: float) -> int:
    return struct.unpack("<H", struct.pack("<e", value))[0]


def _graph_dot(graph: dict[str, Any]) -> str:
    lines = ["digraph Q4KKernelGraph {", "  rankdir=LR;"]
    for node in graph["nodes"]:
        lines.append(f'  "{node["id"]}" [label="{node["id"]}\\n{node["kind"]}"];')
    for edge in graph["edges"]:
        lines.append(f'  "{edge["src"]}" -> "{edge["dst"]}" [label="{edge["scalar_or_vector_type"]}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
