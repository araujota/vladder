from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
from typing import Any
import uuid

from .language_adapter import (
    CLAIM_STATUSES,
    EFFECT_KINDS,
    OBLIGATION_CATEGORIES,
    PROTOCOL_KINDS,
    SEMANTIC_NODE_KINDS,
)
from .lifetime_graph import NODE_KINDS as LIFETIME_NODE_KINDS
from .operator_graph import NODE_KINDS as OPERATOR_NODE_KINDS
from .kernel_graph import KERNEL_NODE_KINDS
from .projection_graph import NODE_KINDS as PROJECTION_NODE_KINDS
from .weight_traversal_graph import NODE_KINDS as WEIGHT_TRAVERSAL_NODE_KINDS


PRIVACY_PROFILE_VERSION = "enterprise-graph-deidentification-v1"
IDENTITY_KEY_SCHEMA_VERSION = "vladder-training-identity-v1"
IDENTITY_SCHEME = "hmac-sha256-consent-epoch"
MAX_GRAPH_NODES = 512
MAX_GRAPH_EDGES = 2048
MAX_ROOTS_PER_BUNDLE = 16
MAX_CANDIDATES_PER_BUNDLE = 128
MAX_OBSERVATIONS_PER_BUNDLE = 512

PUBLIC_NODE_KINDS = frozenset(
    SEMANTIC_NODE_KINDS
    | LIFETIME_NODE_KINDS
    | OPERATOR_NODE_KINDS
    | KERNEL_NODE_KINDS
    | PROJECTION_NODE_KINDS
    | WEIGHT_TRAVERSAL_NODE_KINDS
    | {"Unknown", "Other"}
)
PUBLIC_RELATIONS = frozenset({
    "data", "control", "call", "memory", "state", "lifetime", "ownership",
    "ordering", "alias", "invalidates", "publishes", "consumes", "materializes",
    "transfers", "precedes", "requires_order", "shares_lifetime", "version_transition",
    "read", "write", "flow", "dependency", "other",
})
PUBLIC_OPERATIONS = frozenset({
    "input", "output", "load", "store", "address", "compare", "select", "map",
    "reduce", "scan", "gather", "scatter", "compact", "prefix_scan", "mask",
    "popcount", "pack", "unpack", "decode", "encode", "quantize", "dequantize",
    "add", "sub", "mul", "div", "min", "max", "and", "or", "xor", "shift",
    "branch", "guard", "loop", "call", "return", "allocate", "deallocate",
    "publish", "invalidate", "transfer", "dispatch", "barrier", "fence", "commit",
    "rollback", "materialize", "reuse", "refresh", "retire", "other",
})
PUBLIC_OPERATION_ALIASES = {
    "borrowed_region_inputs": "input",
    "region_observables": "output",
    "bounded_iteration": "loop",
    "memory_read": "load",
    "memory_write": "store",
    "field_projection": "map",
    "predicate": "compare",
    "predicate_mask": "mask",
    "bitvector_transform": "map",
    "bounded_arithmetic": "map",
    "ordered_reduction": "reduce",
    "extent_scan": "prefix_scan",
    "bounded_compaction": "compact",
    "fixed_width_codec": "encode",
    "state_snapshot": "load",
    "state_transition": "commit",
    "owned_realization": "materialize",
    "atomic_transition": "commit",
    "summarized_helper": "call",
    "multi_exit_merge": "return",
    # Canonical operation spellings emitted by executable search grammars. Keep
    # these semantic distinctions while still removing source identifiers.
    "borrowed-u8-sequence": "input",
    "borrowed-contiguous-sequence": "input",
    "projected-bool-field-view": "input",
    "projected-word-field-view": "input",
    "arrow-primitive-values-view": "input",
    "contiguous-forward-traversal": "loop",
    "bounded-source-order-traversal": "loop",
    "load-byte-or-word": "load",
    "load-element-or-word": "load",
    "load-fixed-width-element": "load",
    "element-load": "load",
    "previous-element-load": "load",
    "exact-popcount": "popcount",
    "exact-add": "add",
    "exact-indicator-sum": "reduce",
    "count-true": "compare",
    "count-nonzero": "compare",
    "count-equal": "compare",
    "count-adjacent-changes": "compare",
    "count_true": "compare",
    "count_nonzero": "compare",
    "count_equal": "compare",
    "count_adjacent_changes": "compare",
    "scalar-byte-remainder": "reduce",
    "return-exact-popcount": "output",
    "return-count": "output",
    "typed-live-in": "input",
    "borrowed-state-projection": "map",
    "closed-compiled-region": "map",
    "inlined_into_selected_ir": "call",
    "typed-live-outs": "output",
    "predicate-parameter": "input",
    "ordered-prefix-traversal": "loop",
    "ordered-suffix-traversal": "loop",
    "load-u8": "load",
    "equal-u8": "compare",
    "nonzero-u8": "compare",
    "stop-at-first-false": "guard",
    "ordered-prefix-extent": "reduce",
    "ordered-suffix-extent": "reduce",
    "return-ordered-extent": "output",
    "protocol_boundary": "barrier",
    "ordered-raii-cleanup": "retire",
    "exact_call_preserving": "call",
    "ordered-result-projections": "map",
    "tagged-return-merge": "return",
    "normal-exception-terminate-outcome": "return",
    "atomic-happens-before-projection": "fence",
}
PUBLIC_SCOPES = frozenset({
    "instruction", "expression", "iteration", "loop", "function", "fragment", "record",
    "sequence", "transaction", "frame", "generation", "connection", "process",
    "application", "local", "regional", "composed", "end_to_end", "other",
})
PUBLIC_PLACEMENTS = frozenset({
    "register", "stack", "heap", "arena", "object", "cache", "cpu", "gpu", "device",
    "transport", "network", "storage", "shared", "persistent", "other",
})
PUBLIC_ORDERING = frozenset({
    "none", "relaxed", "acquire", "release", "acq_rel", "seq_cst", "program_order",
    "stable", "unstable", "ordered", "unordered", "before", "after", "other",
})
PUBLIC_PROOF_METHODS = frozenset({
    "z3", "alive2", "smt", "differential", "model_checking", "protocol", "structural",
    "runtime_oracle", "none", "other",
})
PUBLIC_PHASES = frozenset({"before", "during", "after", "entry", "loop", "exit", "commit", "rollback", "other"})
PUBLIC_ARCHITECTURES = frozenset({"x86_64", "aarch64", "arm64", "riscv64", "wasm32", "other"})
PUBLIC_VENDORS = frozenset({"amd", "intel", "arm", "apple", "nvidia", "ibm", "other"})
PUBLIC_MICROARCHITECTURES = frozenset({
    "zen2", "zen3", "zen4", "zen5", "skylake", "icelake", "alderlake", "raptorlake",
    "neoverse_n1", "neoverse_v1", "apple_m1", "apple_m2", "apple_m3", "apple_m4", "other",
})
PUBLIC_ISAS = frozenset({
    "sse4_2", "avx", "avx2", "avx512f", "avx512_vnni", "fma", "bmi2", "popcnt",
    "neon", "sve", "sve2", "rvv", "cuda", "spirv", "portable", "other",
})
PUBLIC_DEVICE_CLASSES = frozenset({"cpu", "gpu", "accelerator", "other"})
PUBLIC_COMPILERS = frozenset({"clang", "gcc", "msvc", "rustc", "zig", "julia", "nvcc", "other"})
PUBLIC_CACHE_REGIMES = frozenset({"l1", "l2", "llc", "streaming", "warm", "cold", "mixed", "other"})
PUBLIC_WORKLOAD_PHASES = PUBLIC_PHASES | frozenset({"prompt", "prefill", "decode", "mixed", "sampling"})
SAFE_NUMERIC_KEYS = frozenset({
    "alignment", "bit_width", "byte_width", "bytes", "cardinality", "count", "depth",
    "dimensions", "distance", "lanes", "levels", "output_count", "rank", "reuse",
    "reuse_distance", "shape", "size", "stride", "trip_count", "vector_width",
})
SAFE_CATEGORY_KEYS = frozenset({
    "alias", "consistency", "determinism", "exactness", "lifetime", "memory_region",
    "mutability", "numerical", "ordering", "ownership", "placement", "representation",
    "scope", "state", "type",
})
SAFE_ACTION_NUMERIC_KEYS = frozenset({
    "accumulators", "batch", "block", "block_size", "depth", "distance", "lanes",
    "execution_width", "factor", "prefetch", "sequence_tile", "tile", "token_tile", "unroll",
    "variant", "vector_width", "width",
})
SAFE_ACTION_CATEGORY_KEYS = frozenset({
    "algorithm", "decision_surface", "direction", "dispatch", "exactness", "isa", "layout", "mode", "order",
    "output", "phase", "realization", "schedule", "tail", "traversal",
})
SAFE_HARDWARE_KEYS = frozenset({
    "architecture", "vendor", "microarchitecture", "device_class", "isa", "vector_width_bits",
    "vector_register_count", "l1d_bytes", "l2_bytes", "l3_bytes", "memory_channels",
    "measured_stream_bandwidth", "compiler_family", "compiler_major",
})
SAFE_WORKLOAD_KEYS = frozenset({
    "input_size", "input_size_bucket", "alignment", "sparsity", "mutation_density",
    "cache_regime", "concurrency", "warm_state", "batch_size", "lifecycle_scope",
    "critical_path_weight", "regional_promotion_floor", "token_count", "sequence_count",
    "context_bucket", "output_cardinality", "phase",
})
SAFE_CONTRACT_KEYS = frozenset({
    "allocation", "aliasing", "alignment", "determinism", "exactness", "exceptions",
    "floating_point", "integer_overflow", "ordering", "output_cardinality", "semantic_family",
    "side_effects", "threading", "trip_count", "bounded", "noexcept",
})
SAFE_RESOURCE_KEYS = frozenset({
    "allocations", "branch_misses", "bytes_moved", "code_size", "cycles", "instructions",
    "l1d_misses", "l2_misses", "llc_misses", "memory_bytes", "stack_bytes", "stalls",
})
SAFE_DECISION_NUMERIC_KEYS = frozenset({
    "action_count", "depth", "factor", "region_count", "remaining_count",
    "selected_count", "tile", "width",
})
SAFE_DECISION_CATEGORY_KEYS = frozenset({
    "delta_kind", "placement", "scope", "stage", "terminal",
})
_SUSPICIOUS_TEXT = re.compile(r"[/\\]|::|\.(?:c|cc|cpp|cxx|h|hpp|rs|zig|jl)(?:$|:)|[A-Fa-f0-9]{32,}")


def default_training_identity_path() -> Path:
    override = os.environ.get("VLADDER_TRAINING_IDENTITY_FILE")
    if override:
        return Path(override).expanduser().resolve()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (config_home / "vladder" / "training-identity.json").resolve()


def load_or_create_training_identity(path: Path | None = None) -> dict[str, Any]:
    identity_path = (path or default_training_identity_path()).expanduser().resolve()
    if identity_path.exists():
        mode = stat.S_IMODE(identity_path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(f"training identity must be owner-only, found mode {mode:o}: {identity_path}")
        value = json.loads(identity_path.read_text())
        if value.get("schema_version") != IDENTITY_KEY_SCHEMA_VERSION:
            raise ValueError(f"unsupported training identity: {identity_path}")
        _identity_key(value)
        return value
    value = {
        "schema_version": IDENTITY_KEY_SCHEMA_VERSION,
        "profile_version": PRIVACY_PROFILE_VERSION,
        "identity_epoch": f"epoch:{uuid.uuid4()}",
        "key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
    }
    _write_private(identity_path, value)
    return value


def rotate_training_identity(path: Path | None = None) -> dict[str, Any]:
    identity_path = (path or default_training_identity_path()).expanduser().resolve()
    value = {
        "schema_version": IDENTITY_KEY_SCHEMA_VERSION,
        "profile_version": PRIVACY_PROFILE_VERSION,
        "identity_epoch": f"epoch:{uuid.uuid4()}",
        "key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
    }
    _write_private(identity_path, value)
    return value


def private_identity(identity: dict[str, Any], namespace: str, value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hmac.new(_identity_key(identity), namespace.encode("ascii") + b"\0" + payload, hashlib.sha256).hexdigest()


def sanitize_root(
    root: dict[str, Any], identity: dict[str, Any], *, project_identity: Any | None = None,
) -> dict[str, Any]:
    graph = root.get("semantic_graph")
    if not isinstance(graph, dict):
        raise ValueError("model-ready export requires a semantic_graph")
    sanitized_graph = sanitize_graph(graph)
    root_id = private_identity(identity, "root", root.get("root_id"))
    languages = sorted({
        str(item.get("source_language", "other")).lower()
        for item in root.get("provenance", []) if isinstance(item, dict)
    }) or ["other"]
    return {
        "root_id": root_id,
        "project_id": private_identity(
            identity, "project", root.get("project_id") if project_identity is None else project_identity,
        ),
        "graph_version": str(root.get("graph_version", "semantic-flow-v2"))[:64],
        "languages": [item if item in {"c", "cpp", "rust", "zig", "julia", "cuda", "spirv", "other"} else "other" for item in languages],
        "graph": sanitized_graph,
        "contract_features": _sanitize_feature_mapping(
            root.get("contract", {}), prefix="contract", allowed=SAFE_CONTRACT_KEYS,
        ),
    }


def sanitize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    raw_nodes = [item for item in graph.get("nodes", []) if isinstance(item, dict)]
    raw_edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    if not raw_nodes or len(raw_nodes) > MAX_GRAPH_NODES:
        raise ValueError(f"model-ready graph must contain 1 to {MAX_GRAPH_NODES} nodes")
    if len(raw_edges) > MAX_GRAPH_EDGES:
        raise ValueError(f"model-ready graph exceeds {MAX_GRAPH_EDGES} edges")
    node_ids = [str(item.get("id", f"node:{index}")) for index, item in enumerate(raw_nodes)]
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("model-ready graph node IDs must be unique before remapping")
    remap = {identifier: index for index, identifier in enumerate(node_ids)}
    nodes = [_sanitize_node(index, item) for index, item in enumerate(raw_nodes)]
    edges = []
    for edge in raw_edges:
        source = str(edge.get("source", edge.get("src", "")))
        destination = str(edge.get("destination", edge.get("dst", "")))
        if source not in remap or destination not in remap:
            raise ValueError("model-ready graph edge references an unknown node")
        edges.append({
            "source": remap[source],
            "destination": remap[destination],
            "relation": _public_value(edge.get("relation", edge.get("kind", "data")), PUBLIC_RELATIONS),
            "ordering": _public_value(edge.get("ordering", "none"), PUBLIC_ORDERING),
            "numeric_features": _sanitize_numeric_mapping(edge, SAFE_NUMERIC_KEYS),
            "categorical_features": _sanitize_category_mapping(edge, SAFE_CATEGORY_KEYS),
        })
    obligations = []
    for item in graph.get("obligations", []):
        if not isinstance(item, dict):
            continue
        obligations.append({
            "category": _public_value(item.get("category", "other"), OBLIGATION_CATEGORIES | {"other"}),
            "scope": _public_value(item.get("scope", "other"), PUBLIC_SCOPES),
            "proof_method": _public_value(item.get("proof_method", "other"), PUBLIC_PROOF_METHODS),
        })
    effects = []
    for item in graph.get("effects", []):
        if not isinstance(item, dict):
            continue
        effects.append({
            "kind": _public_value(item.get("kind", "other"), EFFECT_KINDS | {"other"}),
            "phase": _public_value(item.get("phase", "other"), PUBLIC_PHASES),
            "ordering": _public_value(item.get("ordering", "other"), PUBLIC_ORDERING),
        })
    protocols = []
    for item in graph.get("protocols", []):
        if not isinstance(item, dict):
            continue
        protocols.append({"kind": _public_value(item.get("kind", item.get("protocol", "other")), PROTOCOL_KINDS | {"other"})})
    claims = []
    for item in graph.get("claims", []):
        if not isinstance(item, dict):
            continue
        claims.append({
            "status": _public_value(item.get("status", "unverified"), CLAIM_STATUSES | {"unverified"}),
            "scope": _public_value(item.get("scope", "other"), PUBLIC_SCOPES),
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "obligations": obligations[:128],
        "effects": effects[:128],
        "protocols": protocols[:64],
        "claims": claims[:128],
    }


def sanitize_decision_context(
    value: Any,
    *,
    fallback_graph: dict[str, Any],
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    raw_graph = raw.get("graph") if isinstance(raw.get("graph"), dict) else fallback_graph
    raw_nodes = [item for item in raw_graph.get("nodes", ()) if isinstance(item, dict)]
    node_index = {
        str(item.get("id", f"node:{index}")): index
        for index, item in enumerate(raw_nodes)
    }
    focus = sorted({
        node_index[str(item)]
        for item in raw.get("focus_node_ids", ())
        if str(item) in node_index
    })
    quality = str(raw.get("quality") or "root_only")
    if quality not in {"region_projected", "partial_state", "root_only"}:
        quality = "root_only"
    canonical = (
        raw.get("context", {}).get("canonical_state_hash")
        if isinstance(raw.get("context"), dict) else None
    ) or raw.get("canonical_state_hash")
    return {
        "context_version": str(raw.get("context_version") or "pre-decision-state-v2")[:64],
        "quality": quality,
        "graph": sanitize_graph(raw_graph),
        "focus_node_indices": focus[:128],
        "state_features": _sanitize_decision_features(raw.get("state_features")),
        "semantic_delta": _sanitize_decision_features(raw.get("semantic_delta")),
        "canonical_state_hash": (
            private_identity(identity, "semantic-state", canonical)
            if identity is not None and canonical is not None else None
        ),
    }


def _sanitize_decision_features(value: Any) -> dict[str, Any]:
    numeric: list[dict[str, Any]] = []
    categorical: list[dict[str, Any]] = []
    if not isinstance(value, dict):
        return {"numeric": numeric, "categorical": categorical}
    for raw_key, raw_value in sorted(value.items()):
        key = str(raw_key).lower()
        if (
            key in SAFE_DECISION_NUMERIC_KEYS
            and isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
            and math.isfinite(float(raw_value))
        ):
            numeric.append({"name": key, "value": float(_bucket_number(float(raw_value)))})
        elif key in SAFE_DECISION_CATEGORY_KEYS:
            token = str(raw_value).lower() if isinstance(raw_value, bool) else raw_value
            categorical.append({
                "name": key,
                "value": _safe_generated_token(token, fallback="other"),
            })
    return {"numeric": numeric[:128], "categorical": categorical[:128]}


def sanitize_candidate(
    candidate: dict[str, Any],
    identity: dict[str, Any],
    root_ids: dict[str, str],
) -> dict[str, Any]:
    source_root = str(candidate.get("root_id"))
    if source_root not in root_ids:
        raise ValueError("candidate references a root outside the bundle")
    action = candidate.get("action", {}) if isinstance(candidate.get("action"), dict) else {}
    sanitized_action = sanitize_training_action(action)
    return {
        "candidate_id": private_identity(identity, "candidate", candidate.get("candidate_id")),
        "root_id": root_ids[source_root],
        "baseline": bool(candidate.get("baseline")),
        "action": sanitized_action,
        "hardware": sanitize_training_descriptor(candidate.get("hardware", {}), kind="hardware"),
        "workload": sanitize_training_descriptor(candidate.get("workload", {}), kind="workload"),
    }


def sanitize_training_action(action: dict[str, Any]) -> dict[str, Any]:
    """Return the public structured action shared by v2 candidates and v3 branches."""
    family = _safe_generated_token(action.get("family", "other"), fallback="custom_family")
    primitives = [
        _safe_generated_token(item, fallback="custom_primitive")
        for item in action.get("primitives", []) if isinstance(item, (str, int, float))
    ][:64]
    parameters = action.get("parameters", {}) if isinstance(action.get("parameters"), dict) else {}
    explicit_features = (
        action.get("training_features", {})
        if action.get("public_training_schema") is True and isinstance(action.get("training_features"), dict)
        else {}
    )
    extensions = action.get("extensions", {}) if isinstance(action.get("extensions"), dict) else {}
    return {
        "family": family,
        "family_version": _safe_generated_token(action.get("family_version", action.get("version", "unversioned")), fallback="unversioned"),
        "primitives": primitives,
        "numeric_parameters": _exact_numeric_parameters(parameters, explicit_features, extensions),
        "categorical_parameters": _action_categories(parameters, explicit_features, extensions),
        "extension_namespaces": _public_extension_namespaces(extensions),
    }


def sanitize_training_descriptor(value: Any, *, kind: str) -> dict[str, Any]:
    if kind == "hardware":
        return _sanitize_descriptor(value, SAFE_HARDWARE_KEYS, prefix="hardware")
    if kind == "workload":
        return _sanitize_descriptor(value, SAFE_WORKLOAD_KEYS, prefix="workload")
    if kind == "resource":
        return _sanitize_feature_mapping(value, prefix="resource", allowed=SAFE_RESOURCE_KEYS)
    raise ValueError(f"unknown training descriptor kind: {kind}")


def sanitize_observation(
    observation: dict[str, Any],
    identity: dict[str, Any],
    candidate_ids: dict[str, str],
) -> dict[str, Any]:
    source_candidate = str(observation.get("candidate_id"))
    if source_candidate not in candidate_ids:
        raise ValueError("observation references a candidate outside the bundle")
    payload = observation.get("payload", {}) if isinstance(observation.get("payload"), dict) else {}
    paired = payload.get("paired_speedup", {}) if isinstance(payload.get("paired_speedup"), dict) else {}
    speedup = paired.get("median", payload.get("speedup"))
    low = paired.get("bootstrap_ci_low")
    high = paired.get("bootstrap_ci_high")
    samples = payload.get("sample_count", payload.get("process_count", 0))
    return {
        "observation_id": private_identity(identity, "observation", observation.get("observation_id")),
        "candidate_id": candidate_ids[source_candidate],
        "kind": str(observation.get("kind", "grammar_disposition")),
        "outcome": str(observation.get("outcome", "proof_unknown")),
        "quality_grade": str(observation.get("quality_grade", "D")),
        "proof_class": _safe_generated_token(payload.get("proof_class", payload.get("method", "none")), fallback="other"),
        "benchmark_scope": _benchmark_scope(observation.get("kind"), payload),
        "speedup_percent": _percent_or_none(speedup),
        "ci_lower_percent": _percent_or_none(low),
        "ci_upper_percent": _percent_or_none(high),
        "sample_count": max(0, int(samples)) if isinstance(samples, (int, float)) and math.isfinite(float(samples)) else 0,
        "resource_features": _sanitize_feature_mapping(
            payload.get("resources", {}), prefix="resource", allowed=SAFE_RESOURCE_KEYS,
        ),
    }


def privacy_manifest(identity: dict[str, Any], *, submission_consent: bool) -> dict[str, Any]:
    return {
        "profile_version": PRIVACY_PROFILE_VERSION,
        "risk_classification": "pseudonymized_structural_data",
        "identity_scheme": IDENTITY_SCHEME,
        "identity_epoch": identity["identity_epoch"],
        "topology_included": True,
        "source_included": False,
        "source_identifiers_included": False,
        "raw_literals_included": False,
        "raw_artifacts_included": False,
        "prompts_included": False,
        "personal_data_included": False,
        "submission_consent": submission_consent,
        "residual_risks": ["algorithm_topology_fingerprinting", "within_epoch_record_linkability"],
    }


def search_privacy_manifest(identity: dict[str, Any], *, submission_consent: bool) -> dict[str, Any]:
    value = privacy_manifest(identity, submission_consent=submission_consent)
    value["search_lineage_included"] = True
    value["residual_risks"].append("search_strategy_fingerprinting")
    return value


def _sanitize_node(index: int, node: dict[str, Any]) -> dict[str, Any]:
    kind = _public_value(node.get("kind", "Other"), PUBLIC_NODE_KINDS, preserve_case=True)
    raw_operation = str(node.get("operation", kind)).lower()
    operation = _public_value(PUBLIC_OPERATION_ALIASES.get(raw_operation, raw_operation), PUBLIC_OPERATIONS)
    output_type = node.get("output_type", node.get("type"))
    type_class, bit_width, lanes = _type_shape(output_type)
    public_features = dict(node)
    attributes = node.get("attributes")
    if isinstance(attributes, dict):
        for name, value in attributes.items():
            if name in SAFE_NUMERIC_KEYS or name in SAFE_CATEGORY_KEYS:
                public_features.setdefault(name, value)
    return {
        "index": index,
        "kind": kind,
        "operation": operation,
        "type_class": type_class,
        "bit_width": bit_width,
        "vector_lanes": lanes,
        "numeric_features": _sanitize_numeric_mapping(public_features, SAFE_NUMERIC_KEYS),
        "categorical_features": _sanitize_category_mapping(public_features, SAFE_CATEGORY_KEYS),
    }


def _type_shape(value: Any) -> tuple[str, int | None, int | None]:
    text = str(value or "").lower()
    lanes_match = re.search(r"<\s*(\d+)\s*x", text)
    width_match = re.search(r"(?:i|u|f)(8|16|32|64|128)\b", text)
    lanes = _bucket_integer(int(lanes_match.group(1))) if lanes_match else None
    width = int(width_match.group(1)) if width_match else None
    if "ptr" in text or "*" in text or "pointer" in text:
        kind = "pointer"
    elif re.search(r"\b(?:f16|f32|f64|float|double|half)\b", text):
        kind = "float"
    elif re.search(r"\b(?:i|u)(?:8|16|32|64|128)\b", text) or "int" in text:
        kind = "integer"
    elif "bool" in text or "i1" in text:
        kind = "boolean"
    elif "[" in text or "struct" in text or "aggregate" in text:
        kind = "aggregate"
    elif not text:
        kind = "unknown"
    else:
        kind = "other"
    return kind, width, lanes


def _sanitize_numeric_mapping(value: dict[str, Any], allowed: frozenset[str]) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    for raw_key, raw_value in sorted(value.items()):
        key = str(raw_key).lower()
        if key not in allowed:
            continue
        values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
        for index, item in enumerate(values[:8]):
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
                continue
            name = key if len(values) == 1 else f"{key}_{index}"
            result.append({"name": name, "value": float(_bucket_number(float(item)))})
    return result[:64]


def _sanitize_category_mapping(value: dict[str, Any], allowed: frozenset[str]) -> list[dict[str, str]]:
    result = []
    for raw_key, raw_value in sorted(value.items()):
        key = str(raw_key).lower()
        if key not in allowed or isinstance(raw_value, (dict, list, tuple)):
            continue
        vocabulary = PUBLIC_SCOPES if key in {"scope", "lifetime"} else PUBLIC_ORDERING if key == "ordering" else PUBLIC_PLACEMENTS if key in {"placement", "memory_region"} else None
        result.append({"name": key, "value": _public_value(raw_value, vocabulary or frozenset({"true", "false", "mutable", "immutable", "read", "write", "exact", "tolerance", "other"}))})
    return result[:32]


def _sanitize_feature_mapping(
    value: Any, *, prefix: str, allowed: frozenset[str],
) -> dict[str, Any]:
    numeric: list[dict[str, float]] = []
    categorical: list[dict[str, str]] = []
    if isinstance(value, dict):
        for raw_key, raw_value in sorted(value.items()):
            key = str(raw_key).lower()
            if key not in allowed:
                continue
            name = f"{prefix}.{key}"[:96]
            if isinstance(raw_value, bool):
                categorical.append({"name": name, "value": str(raw_value).lower()})
            elif isinstance(raw_value, (int, float)) and math.isfinite(float(raw_value)):
                numeric.append({"name": name, "value": float(_bucket_number(float(raw_value)))})
            elif key in SAFE_CATEGORY_KEYS:
                categorical.append({"name": name, "value": "other"})
    return {"numeric": numeric[:128], "categorical": categorical[:128]}


def _sanitize_descriptor(value: Any, allowed: frozenset[str], *, prefix: str) -> dict[str, Any]:
    numeric: list[dict[str, float]] = []
    categorical: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return {"numeric": numeric, "categorical": categorical}
    for raw_key, raw_value in sorted(value.items()):
        key = str(raw_key).lower()
        if key not in allowed:
            continue
        name = f"{prefix}.{key}"[:96]
        if isinstance(raw_value, bool):
            categorical.append({"name": name, "value": str(raw_value).lower()})
        elif isinstance(raw_value, (int, float)) and math.isfinite(float(raw_value)):
            numeric.append({"name": name, "value": float(_bucket_number(float(raw_value)))})
        elif isinstance(raw_value, (list, tuple)):
            for item in raw_value[:32]:
                categorical.append({"name": name, "value": _descriptor_category(prefix, key, item)})
        else:
            categorical.append({"name": name, "value": _descriptor_category(prefix, key, raw_value)})
    return {"numeric": numeric[:128], "categorical": categorical[:128]}


def _exact_numeric_parameters(
    parameters: dict[str, Any], explicit: dict[str, Any], extensions: dict[str, Any],
) -> list[dict[str, float]]:
    result = []
    for raw_key, value in sorted(parameters.items()):
        key = str(raw_key).lower()
        if key in SAFE_ACTION_NUMERIC_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            result.append({"name": key, "value": float(value)})
    for namespace, values in _declared_training_features(explicit, extensions, "numeric"):
        for raw_key, value in sorted(values.items()):
            key = _safe_generated_token(f"{namespace}.{raw_key}" if namespace else raw_key, fallback="other")
            if key != "other" and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                result.append({"name": key, "value": float(value)})
    return _deduplicate_features(result)[:64]


def _descriptor_category(prefix: str, key: str, value: Any) -> str:
    if prefix == "hardware":
        vocabulary = {
            "architecture": PUBLIC_ARCHITECTURES,
            "vendor": PUBLIC_VENDORS,
            "microarchitecture": PUBLIC_MICROARCHITECTURES,
            "device_class": PUBLIC_DEVICE_CLASSES,
            "isa": PUBLIC_ISAS,
            "compiler_family": PUBLIC_COMPILERS,
        }.get(key, frozenset({"other"}))
    else:
        vocabulary = {
            "cache_regime": PUBLIC_CACHE_REGIMES,
            "lifecycle_scope": PUBLIC_SCOPES,
            "phase": PUBLIC_WORKLOAD_PHASES,
            "warm_state": frozenset({"true", "false", "warm", "cold", "other"}),
        }.get(key, frozenset({"other"}))
    return _public_value(value, vocabulary)


def _action_categories(
    parameters: dict[str, Any], explicit: dict[str, Any], extensions: dict[str, Any],
) -> list[dict[str, str]]:
    result = []
    for raw_key, value in sorted(parameters.items()):
        key = str(raw_key).lower()
        if key in SAFE_ACTION_CATEGORY_KEYS and not isinstance(value, (dict, list, tuple)):
            result.append({"name": key, "value": _safe_generated_token(value, fallback="other")})
    for namespace, values in _declared_training_features(explicit, extensions, "categorical"):
        for raw_key, value in sorted(values.items()):
            key = _safe_generated_token(f"{namespace}.{raw_key}" if namespace else raw_key, fallback="other")
            token = _safe_generated_token(value, fallback="other")
            if key != "other" and token != "other":
                result.append({"name": key, "value": token})
    return _deduplicate_features(result)[:64]


def _declared_training_features(
    explicit: dict[str, Any], extensions: dict[str, Any], kind: str,
) -> list[tuple[str, dict[str, Any]]]:
    values: list[tuple[str, dict[str, Any]]] = []
    direct = explicit.get(kind)
    if isinstance(direct, dict):
        values.append(("", direct))
    for raw_namespace, extension in sorted(extensions.items()):
        if not isinstance(extension, dict) or extension.get("public_training_schema") is not True:
            continue
        features = extension.get("training_features", {})
        selected = features.get(kind) if isinstance(features, dict) else None
        namespace = _safe_generated_token(raw_namespace, fallback="other")
        if namespace != "other" and isinstance(selected, dict):
            values.append((namespace, selected))
    return values


def _public_extension_namespaces(extensions: dict[str, Any]) -> list[str]:
    result = []
    for namespace, payload in sorted(extensions.items()):
        if isinstance(payload, dict) and payload.get("public_training_schema") is True:
            token = _safe_generated_token(namespace, fallback="other")
            if token != "other":
                result.append(token)
    return result[:8]


def _deduplicate_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for feature in features:
        result[str(feature["name"])] = feature
    return [result[key] for key in sorted(result)]


def _benchmark_scope(kind: Any, payload: dict[str, Any]) -> str:
    value = str(payload.get("benchmark_scope", ""))
    if value in {"none", "micro", "regional", "composed", "end_to_end"}:
        return value
    return "composed" if kind == "composition" else "micro" if kind == "benchmark" else "none"


def _public_value(value: Any, vocabulary: frozenset[str] | set[str], *, preserve_case: bool = False) -> str:
    text = str(value or "other")
    if text in vocabulary:
        return text
    lowered = text.lower()
    lookup = {str(item).lower(): str(item) for item in vocabulary}
    if lowered in lookup:
        return lookup[lowered] if preserve_case else lowered
    return "Other" if preserve_case else "other"


def _safe_generated_token(value: Any, *, fallback: str) -> str:
    text = str(value or fallback).strip()
    if not text or len(text) > 96 or _SUSPICIOUS_TEXT.search(text):
        return fallback
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+/-]*", text):
        return fallback
    return text


def _bucket_number(value: float) -> float:
    if value == 0:
        return 0.0
    sign = -1.0 if value < 0 else 1.0
    magnitude = abs(value)
    if magnitude < 1:
        return sign * (2.0 ** math.floor(math.log2(magnitude)))
    return sign * float(2 ** int(math.floor(math.log2(magnitude))))


def _bucket_integer(value: int) -> int:
    return int(_bucket_number(float(max(1, value))))


def _finite_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) else None


def _percent_or_none(value: Any) -> float | None:
    finite = _finite_or_none(value)
    return finite * 100.0 if finite is not None else None


def _identity_key(value: dict[str, Any]) -> bytes:
    try:
        key = base64.urlsafe_b64decode(str(value["key"]).encode("ascii"))
    except Exception as error:
        raise ValueError("invalid training identity key") from error
    if len(key) != 32:
        raise ValueError("training identity key must contain 256 bits")
    return key


def _write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".training-identity-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
