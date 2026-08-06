from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import bounded_artifact_path

from .language_adapter import canonical_hash


SEMANTIC_CLOSURE_SCHEMA = "semantic-closure-v1"

EFFECT_FLAGS = frozenset({
    "allocate",
    "deallocate",
    "cleanup",
    "unwind",
    "synchronize",
    "atomic",
    "volatile",
    "publish",
    "invalidate",
    "external_io",
    "callback",
    "nondeterminism",
    "nontermination",
})
CALL_KINDS = frozenset({"intrinsic", "definition", "finite_dispatch", "protocol", "opaque"})
PROOF_AUTHORITIES = frozenset({
    "compiler-attribute",
    "definition-hash",
    "functional-proof",
    "protocol-proof",
    "contract",
    "opaque",
})
CROSSING_POLICIES = frozenset({"permitted", "call-preserving-only", "forbidden"})


def _normalized(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


@dataclass(frozen=True)
class EffectFootprint:
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    unknown: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "reads", _normalized(self.reads))
        object.__setattr__(self, "writes", _normalized(self.writes))
        object.__setattr__(self, "flags", _normalized(self.flags))
        invalid = set(self.flags) - EFFECT_FLAGS
        if invalid:
            raise ValueError(f"unknown effect flags: {sorted(invalid)}")

    def join(self, *others: EffectFootprint) -> EffectFootprint:
        reads = set(self.reads)
        writes = set(self.writes)
        flags = set(self.flags)
        unknown = self.unknown
        for other in others:
            reads.update(other.reads)
            writes.update(other.writes)
            flags.update(other.flags)
            unknown = unknown or other.unknown
        return EffectFootprint(tuple(reads), tuple(writes), tuple(flags), unknown)

    def contains(self, other: EffectFootprint) -> bool:
        return (
            set(other.reads) <= set(self.reads)
            and set(other.writes) <= set(self.writes)
            and set(other.flags) <= set(self.flags)
            and (not other.unknown or self.unknown)
        )

    @property
    def externally_observable(self) -> bool:
        return self.unknown or bool(set(self.flags) & {
            "unwind", "synchronize", "atomic", "volatile", "publish", "invalidate",
            "external_io", "callback", "nondeterminism", "nontermination",
        })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> EffectFootprint:
        value = value or {}
        return cls(
            tuple(value.get("reads", ())),
            tuple(value.get("writes", ())),
            tuple(value.get("flags", ())),
            bool(value.get("unknown", False)),
        )


@dataclass(frozen=True)
class CallRelation:
    id: str
    caller: str
    targets: tuple[str, ...]
    kind: str
    callsite: str
    effects: EffectFootprint
    argument_ownership: tuple[str, ...] = ()
    result_channels: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    authority: str = "opaque"
    crossing: str = "forbidden"
    protocol: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.caller or not self.callsite:
            raise ValueError("call relation identity, caller, and callsite are required")
        if self.kind not in CALL_KINDS:
            raise ValueError(f"unknown call relation kind: {self.kind}")
        if self.authority not in PROOF_AUTHORITIES:
            raise ValueError(f"unknown call authority: {self.authority}")
        if self.crossing not in CROSSING_POLICIES:
            raise ValueError(f"unknown crossing policy: {self.crossing}")
        object.__setattr__(self, "targets", _normalized(self.targets))
        object.__setattr__(self, "argument_ownership", tuple(self.argument_ownership))
        object.__setattr__(self, "result_channels", tuple(self.result_channels))
        object.__setattr__(self, "preconditions", tuple(self.preconditions))
        object.__setattr__(self, "postconditions", tuple(self.postconditions))
        if self.kind in {"definition", "finite_dispatch"} and not self.targets:
            raise ValueError(f"{self.kind} relation requires at least one target")
        if self.kind == "opaque" and self.crossing != "forbidden":
            raise ValueError("opaque relations cannot permit transformation crossing")
        if self.kind == "protocol" and not self.protocol:
            raise ValueError("protocol relation requires a protocol envelope name")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "effects": self.effects.to_dict()}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CallRelation:
        return cls(
            id=str(value["id"]),
            caller=str(value["caller"]),
            targets=tuple(value.get("targets", ())),
            kind=str(value["kind"]),
            callsite=str(value["callsite"]),
            effects=EffectFootprint.from_dict(value.get("effects")),
            argument_ownership=tuple(value.get("argument_ownership", ())),
            result_channels=tuple(value.get("result_channels", ())),
            preconditions=tuple(value.get("preconditions", ())),
            postconditions=tuple(value.get("postconditions", ())),
            authority=str(value.get("authority", "opaque")),
            crossing=str(value.get("crossing", "forbidden")),
            protocol=value.get("protocol"),
            provenance=dict(value.get("provenance", {})),
        )


@dataclass(frozen=True)
class FunctionSummary:
    id: str
    source_language: str
    compiler_identity: str
    body_hash: str
    semantic_graph_hash: str
    local_effects: EffectFootprint
    calls: tuple[CallRelation, ...] = ()
    candidate_count: int = 0
    contracts: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.source_language or not self.compiler_identity:
            raise ValueError("function summary identity, language, and compiler are required")
        if self.candidate_count < 0:
            raise ValueError("candidate_count cannot be negative")
        call_ids = [item.id for item in self.calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError(f"duplicate call relation in {self.id}")
        if any(item.caller != self.id for item in self.calls):
            raise ValueError(f"call relation caller does not match function {self.id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_language": self.source_language,
            "compiler_identity": self.compiler_identity,
            "body_hash": self.body_hash,
            "semantic_graph_hash": self.semantic_graph_hash,
            "local_effects": self.local_effects.to_dict(),
            "calls": [item.to_dict() for item in self.calls],
            "candidate_count": self.candidate_count,
            "contracts": self.contracts,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FunctionSummary:
        return cls(
            id=str(value["id"]),
            source_language=str(value["source_language"]),
            compiler_identity=str(value["compiler_identity"]),
            body_hash=str(value.get("body_hash", "")),
            semantic_graph_hash=str(value.get("semantic_graph_hash", "")),
            local_effects=EffectFootprint.from_dict(value.get("local_effects")),
            calls=tuple(CallRelation.from_dict(item) for item in value.get("calls", ())),
            candidate_count=int(value.get("candidate_count", 0)),
            contracts=dict(value.get("contracts", {})),
        )


def _strongly_connected_components(adjacency: dict[str, set[str]]) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(adjacency[node]):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            components.append(tuple(sorted(component)))

    for node in sorted(adjacency):
        if node not in indices:
            visit(node)
    return sorted(components, key=lambda item: item[0])


def compose_system_graph(name: str, functions: Iterable[FunctionSummary]) -> dict[str, Any]:
    materialized = tuple(functions)
    by_id = {item.id: item for item in materialized}
    if not by_id:
        raise ValueError("system graph requires at least one function")
    if len(by_id) != len(materialized):
        raise ValueError("function summary identifiers must be unique")
    adjacency = {name: set() for name in by_id}
    boundaries: list[dict[str, Any]] = []
    for function in by_id.values():
        for relation in function.calls:
            local_targets = set(relation.targets) & set(by_id)
            adjacency[function.id].update(local_targets)
            missing = sorted(set(relation.targets) - set(by_id))
            opaque = relation.kind == "opaque" or bool(missing) or relation.effects.unknown
            if opaque:
                boundaries.append({
                    "id": relation.id,
                    "caller": function.id,
                    "callsite": relation.callsite,
                    "native_construct": relation.provenance.get("native_construct", relation.callsite),
                    "missing_targets": missing,
                    "missing_contract": relation.provenance.get(
                        "missing_contract", "finite functional relation and effect/protocol summary"
                    ),
                    "effect_dimensions": relation.effects.to_dict(),
                    "excluded_claim": "semantic equivalence across this call or protocol boundary",
                    "next_action": relation.provenance.get(
                        "next_action", "declare a finite target/functional summary or keep the call boundary-preserving"
                    ),
                })
        for index, residual in enumerate(function.contracts.get("residual_boundaries", [])):
            boundaries.append({
                "id": f"{function.id}.semantic.{index}",
                "caller": function.id,
                "callsite": "selected-function semantic capture",
                "native_construct": str(residual.get("kind", "unmodeled semantic construct")),
                "missing_targets": [],
                "missing_contract": str(residual.get("reason", residual.get("kind", "semantic closure"))),
                "effect_dimensions": function.local_effects.to_dict(),
                "excluded_claim": "complete computational semantic closure for this selected function",
                "next_action": str(residual.get("required_adapter", "provide the named semantic adapter")),
            })

    components = _strongly_connected_components(adjacency)
    transitive = {identifier: summary.local_effects for identifier, summary in by_id.items()}
    maximum_iterations = max(1, len(by_id) * (len(EFFECT_FLAGS) + len(by_id) + 2))
    iterations = 0
    while iterations < maximum_iterations:
        iterations += 1
        changed = False
        updated: dict[str, EffectFootprint] = {}
        for identifier in sorted(by_id):
            summary = by_id[identifier]
            value = summary.local_effects
            for relation in summary.calls:
                value = value.join(relation.effects)
                for target in relation.targets:
                    if target in transitive:
                        value = value.join(transitive[target])
            updated[identifier] = value
            changed = changed or value != transitive[identifier]
        transitive = updated
        if not changed:
            break
    else:
        raise RuntimeError("effect-summary fixpoint did not converge")

    boundary_callers = {item["caller"] for item in boundaries}
    function_rows = []
    for identifier in sorted(by_id):
        summary = by_id[identifier]
        function_rows.append({
            **summary.to_dict(),
            "transitive_effects": transitive[identifier].to_dict(),
            "effect_closure": "partial" if transitive[identifier].unknown else "closed",
            "semantic_capture": summary.contracts.get("semantic_capture", "unspecified"),
            "closure": "partial_with_local_subgraphs" if identifier in boundary_callers else "closed",
        })
    recursive = [
        list(component) for component in components
        if len(component) > 1 or any(member in adjacency[member] for member in component)
    ]
    payload = {
        "schema_version": SEMANTIC_CLOSURE_SCHEMA,
        "name": name,
        "functions": function_rows,
        "edges": [
            {"source": source, "destination": target}
            for source in sorted(adjacency) for target in sorted(adjacency[source])
        ],
        "components": [list(item) for item in components],
        "recursive_components": recursive,
        "boundaries": sorted(boundaries, key=lambda item: item["id"]),
        "fixpoint_iterations": iterations,
        "computational_candidate_count": sum(item.candidate_count for item in by_id.values()),
        "protocol_summary_candidate_count": 0,
        "search_space_policy": "protocol summaries constrain legality and proof; they are not candidate dimensions",
        "closure": "closed" if not boundaries else "partial_with_local_subgraphs",
    }
    return {**payload, "graph_hash": canonical_hash(payload)}


def prove_system_graph(graph: dict[str, Any], output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    try:
        import z3
    except ImportError:
        return {
            "schema_version": SEMANTIC_CLOSURE_SCHEMA,
            "status": "UNAVAILABLE",
            "method": "Z3",
            "obligations": [],
        }

    functions = {item["id"]: item for item in graph.get("functions", [])}
    effect_values = []
    for function in functions.values():
        effect_values.extend((function["local_effects"], function["transitive_effects"]))
        effect_values.extend(relation["effects"] for relation in function.get("calls", []))
    dimensions = {f"flag:{name}" for name in EFFECT_FLAGS}
    for value in effect_values:
        dimensions.update(f"read:{name}" for name in value.get("reads", []))
        dimensions.update(f"write:{name}" for name in value.get("writes", []))
    dimensions.add("unknown")
    bits = {name: index for index, name in enumerate(sorted(dimensions))}

    def mask(value: dict[str, Any]) -> int:
        result = 0
        for flag in value.get("flags", []):
            result |= 1 << bits[f"flag:{flag}"]
        for region in value.get("reads", []):
            result |= 1 << bits[f"read:{region}"]
        for region in value.get("writes", []):
            result |= 1 << bits[f"write:{region}"]
        if value.get("unknown"):
            result |= 1 << bits["unknown"]
        return result

    obligations = []
    for identifier, function in sorted(functions.items()):
        expected = mask(function["local_effects"])
        for relation in function.get("calls", []):
            expected |= mask(relation["effects"])
            for target in relation.get("targets", []):
                if target in functions:
                    expected |= mask(functions[target]["transitive_effects"])
        actual = mask(function["transitive_effects"])
        solver = z3.Solver()
        width = len(bits)
        solver.add(z3.BitVecVal(actual, width) != z3.BitVecVal(expected, width))
        result = solver.check()
        artifact = bounded_artifact_path(output_directory, "summary-join", identifier, ".smt2")
        artifact.write_text(solver.to_smt2())
        obligations.append({
            "id": f"summary-join:{identifier}",
            "full_identity": identifier,
            "status": "PASS" if result == z3.unsat else "FAIL",
            "method": "Z3 finite effect-lattice equality",
            "artifact": str(artifact),
        })

    candidate_solver = z3.Solver()
    computational = int(graph.get("computational_candidate_count", 0))
    protocol = int(graph.get("protocol_summary_candidate_count", -1))
    candidate_solver.add(z3.IntVal(computational + protocol) != z3.IntVal(computational))
    candidate_result = candidate_solver.check()
    candidate_artifact = output_directory / "search-space-separation.smt2"
    candidate_artifact.write_text(candidate_solver.to_smt2())
    obligations.append({
        "id": "search-space-separation",
        "status": "PASS" if candidate_result == z3.unsat else "FAIL",
        "method": "Z3 candidate-cardinality invariant",
        "artifact": str(candidate_artifact),
    })
    status = "PASS" if all(item["status"] == "PASS" for item in obligations) else "FAIL"
    return {
        "schema_version": SEMANTIC_CLOSURE_SCHEMA,
        "status": status,
        "method": "Z3 + deterministic summary composition",
        "obligations": obligations,
        "claim_boundary": (
            "summary composition and candidate-cardinality separation only; local functional "
            "refinement and external protocols require their declared proof methods"
        ),
    }
