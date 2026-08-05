from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .prior_data import PriorExperienceStore, make_candidate, make_observation, make_root


FAMILIES = (
    "stable_compaction", "wire_codec", "stateful_delta", "aos_fused_reduction",
    "lifetime_extension", "gpu_schedule",
)
LANGUAGES = ("c", "cpp", "rust", "zig", "julia")


def generate_synthetic_prior_corpus(output_directory: Path, *, root_count: int = 60) -> dict[str, Any]:
    output_directory = output_directory.resolve(); output_directory.mkdir(parents=True, exist_ok=True)
    store = PriorExperienceStore(output_directory / "experience")
    roots = []; candidates = []; observations = []
    for ordinal in range(root_count):
        family = FAMILIES[ordinal % len(FAMILIES)]
        language = LANGUAGES[ordinal % len(LANGUAGES)]
        graph = _graph_for_family(family, ordinal)
        contract = {
            "exact": True, "stable_order": family == "stable_compaction",
            "size_bucket": 1 << (4 + ordinal % 8), "semantic_family": family,
            "controlled_root_variant": ordinal,
            "capacity_failure": "unchanged_state" if family in {"stable_compaction", "stateful_delta"} else "not_applicable",
        }
        root = make_root(graph, contract, [{
            "source_language": language, "frontend_version": f"synthetic-{language}-v0",
            "source_commit": f"fixture-{ordinal // 10}", "source_region_hash": f"region-{ordinal}",
        }], project_id=f"synthetic-project-{ordinal % 12}")
        roots.append(root)
        hardware = _hardware(ordinal)
        workload = {
            "input_size_bucket": contract["size_bucket"], "alignment": 32 if ordinal % 2 == 0 else 8,
            "sparsity": (ordinal % 5) / 5.0, "cache_regime": ("l2", "llc", "streaming")[ordinal % 3],
            "critical_path_weight": 0.1 + (ordinal % 5) * 0.15, "promotion_floor": 0.03,
        }
        baseline = make_candidate(root["root_id"], {"family": "baseline", "version": 1, "parameters": {}}, hardware, workload, baseline=True)
        candidates.append(baseline)
        observations.extend(_observations(baseline, 0.0, "statistical_tie"))
        for candidate_family in FAMILIES:
            for variant in range(5):
                action = {
                    "family": candidate_family, "version": 1,
                    "parameters": {
                        "variant": variant, "isa": "avx2" if variant == 1 else "experimental" if variant == 2 else "portable",
                        "execution_width": 32 if variant == 1 else 64 if variant == 2 else 8,
                        "order": "stable" if candidate_family == "stable_compaction" else "declared",
                    },
                }
                candidate = make_candidate(root["root_id"], action, hardware, workload, derivation=[f"{candidate_family}.v{variant}"])
                candidates.append(candidate)
                applicable = candidate_family == family
                if applicable:
                    hardware_bonus = 0.05 if variant == 1 and "avx2" in hardware["isa"] else -0.02 if variant == 1 else -0.08 - 0.01 * variant if variant >= 2 else 0.0
                    utility = 0.10 + (ordinal % 4) * 0.025 + hardware_bonus
                    outcome = "material_regional_win" if utility >= 0.03 else "small_win_below_floor"
                elif candidate_family == FAMILIES[(ordinal + 1) % len(FAMILIES)]:
                    utility = 0.0; outcome = "compiler_identical"
                else:
                    utility = -0.04 - 0.01 * variant; outcome = "measured_regression"
                observations.extend(_observations(candidate, utility, outcome, applicable=applicable))
    store.append("roots", roots); store.append("candidates", candidates); store.append("observations", observations)
    dataset = store.load()
    canonicalization = _multilingual_canonicalization()
    (output_directory / "multilingual-canonicalization.json").write_text(json.dumps(canonicalization, indent=2, sort_keys=True) + "\n")
    report = {
        "schema_version": "vladder-prior-synthetic-corpus-v0", "status": "pass",
        "experience_store": str(store.root), "dataset_hash": dataset["dataset_hash"],
        "root_count": len(roots), "candidate_count": len(candidates), "observation_count": len(observations),
        "multilingual_canonicalization": canonicalization,
        "claim_boundary": "controlled Grade C pilot data; not production physical evidence",
    }
    (output_directory / "synthetic-corpus-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _multilingual_canonicalization() -> dict[str, Any]:
    rows = []
    for family_ordinal, family in enumerate(FAMILIES):
        contract = {"exact": True, "semantic_family": family, "canonical_clone": True}
        identities = {
            language: make_root(
                _graph_for_family(family, family_ordinal), contract,
                [{"source_language": language, "frontend_version": f"synthetic-{language}-v0"}],
                project_id=f"canonical-clone-{family}",
            )["root_id"]
            for language in LANGUAGES
        }
        rows.append({"family": family, "identities": identities, "equivalent_identity": len(set(identities.values())) == 1})
    return {
        "schema_version": "vladder-prior-multilingual-canonicalization-v0",
        "status": "pass" if all(item["equivalent_identity"] for item in rows) else "fail",
        "languages": list(LANGUAGES), "rows": rows,
        "claim_boundary": "canonical identity equality only; not source-language semantic equivalence proof",
    }


def _graph_for_family(family: str, ordinal: int) -> dict[str, Any]:
    kinds = {
        "stable_compaction": ("Input", "Compare", "Mask", "PrefixScan", "Compact", "Extent", "Output"),
        "wire_codec": ("Input", "CapacityGuard", "EndianConvert", "Bitwise", "Codec", "Output"),
        "stateful_delta": ("StateRead", "Compare", "Compact", "Commit", "Rollback", "StateWrite", "Output"),
        "aos_fused_reduction": ("Input", "Project", "Compare", "Reduce", "Histogram", "Output"),
        "lifetime_extension": ("Input", "Materialize", "LifetimeBoundary", "StateRead", "Output"),
        "gpu_schedule": ("Input", "DispatchGrid", "Workgroup", "Lane", "GlobalMemoryTransaction", "Output"),
    }[family]
    nodes = [{
        "id": f"n{index}", "kind": kind, "operation": f"{family}.{kind.lower()}",
        "inputs": [] if index == 0 else [f"n{index - 1}"], "output_type": "u32",
        "attributes": {"ordinal_bucket": ordinal % 3 if kind in {"Input", "Output"} else 0},
        "source_provenance": {"language": "intentionally-ignored"}, "semantic_obligations": [],
    } for index, kind in enumerate(kinds)]
    edges = [{
        "id": f"e{index}", "source": f"n{index}", "destination": f"n{index + 1}",
        "value_type": "u32", "ownership": "borrowed", "lifetime": "call",
        "ordering": "program-order", "realization": "semantic", "memory_region": "argument",
        "validity_scope": "bounded-root",
    } for index in range(len(nodes) - 1)]
    return {
        "schema_version": "semantic-flow-v2", "name": f"synthetic-{family}", "source_language": "ignored",
        "nodes": nodes, "edges": edges, "obligations": [], "effects": [], "protocols": [], "claims": [],
        "contracts": {"family": family},
    }


def _hardware(ordinal: int) -> dict[str, Any]:
    if ordinal % 2 == 0:
        return {
            "architecture": "x86_64", "vendor": "AMD", "model_family": "Zen4", "device_class": "cpu",
            "isa": ["sse4_2", "avx2", "bmi2", "popcnt"], "vector_width_bits": 256,
            "vector_register_count": 16, "l1d_bytes": 32768, "l2_bytes_per_core": 1048576,
            "measured_stream_bandwidth": 45_000_000_000, "compiler": {"family": "clang", "major": 20},
        }
    return {
        "architecture": "aarch64", "vendor": "ARM", "model_family": "Neoverse", "device_class": "cpu",
        "isa": ["neon"], "vector_width_bits": 128, "vector_register_count": 32,
        "l1d_bytes": 65536, "l2_bytes_per_core": 1048576, "measured_stream_bandwidth": 35_000_000_000,
        "compiler": {"family": "clang", "major": 20},
    }


def _observations(candidate: dict[str, Any], utility: float, outcome: str, *, applicable: bool = True) -> list[dict[str, Any]]:
    semantic_outcome = "proof_passed" if applicable or candidate["baseline"] else "inapplicable"
    return [
        make_observation(candidate["candidate_id"], "proof", semantic_outcome, {"method": "synthetic exact oracle"}, quality_grade="C"),
        make_observation(candidate["candidate_id"], "benchmark", outcome, {
            "paired_speedup": {"median": utility, "bootstrap_ci_low": utility - 0.005, "bootstrap_ci_high": utility + 0.005},
            "process_count": 10, "binary_hash": candidate["candidate_id"][:32], "synthetic": True,
        }, quality_grade="C"),
    ]
