from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from .dataflow_ir import BoundedDataflowContract, build_bounded_dataflow_graph
from .language_adapter import canonical_hash


@dataclass(frozen=True)
class DataflowRule:
    family: str
    id: str
    source: str
    target: str
    proof: tuple[str, ...]
    cost_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataflowDerivation:
    family: str
    source: str
    target: str
    rules: tuple[DataflowRule, ...]
    source_graph_hash: str
    target_graph_hash: str
    proof_obligations: tuple[str, ...]
    derivation_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "rules": [item.to_dict() for item in self.rules],
            "proof_obligations": list(self.proof_obligations),
        }


class BoundedDataflowGrammar:
    def __init__(self, payload: dict[str, Any], source: str) -> None:
        self.payload = payload
        self.source = source
        self.version = str(payload["version"])
        self.hash = canonical_hash(payload)
        self.terminals = {str(key): dict(value) for key, value in payload["terminals"].items()}
        rules: list[DataflowRule] = []
        self.sources: dict[str, str] = {}
        for family in payload["families"]:
            family_id = str(family["id"])
            source_state = str(family["source"])
            self.sources[family_id] = source_state
            for item in family["rules"]:
                rules.append(DataflowRule(
                    family_id,
                    str(item["id"]),
                    source_state,
                    str(item["to"]),
                    tuple(str(value) for value in item["proof"]),
                    tuple(str(value) for value in item["cost_signals"]),
                ))
        self.rules = tuple(rules)
        self._validate()

    def _validate(self) -> None:
        if self.payload.get("schema_version") != "vladder-bounded-dataflow-grammar-v1":
            raise ValueError("unsupported bounded dataflow grammar schema")
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"duplicate bounded dataflow rule: {rule.id}")
            seen.add(rule.id)
            if not rule.proof or not rule.cost_signals:
                raise ValueError(f"bounded dataflow rule lacks proof or cost evidence: {rule.id}")
            if rule.target not in self.terminals:
                raise ValueError(f"bounded dataflow rule target has no terminal: {rule.target}")
            if self.terminals[rule.target].get("family") != rule.family:
                raise ValueError(f"bounded dataflow terminal family mismatch: {rule.target}")
        for family, source in self.sources.items():
            if source not in self.terminals or self.terminals[source].get("family") != family:
                raise ValueError(f"bounded dataflow source terminal missing: {family}/{source}")

    def family_terminals(self, family: str) -> tuple[str, ...]:
        if family not in self.sources:
            raise ValueError(f"unknown bounded dataflow family: {family}")
        return tuple(sorted(name for name, value in self.terminals.items() if value.get("family") == family))

    def coverage(self) -> dict[str, Any]:
        families = []
        for family in sorted(self.sources):
            family_rules = [item for item in self.rules if item.family == family]
            terminals = self.family_terminals(family)
            lowering_classes = {
                "cpp": {terminal: "native_physical" for terminal in terminals},
            }
            for language in ("c", "rust", "zig", "julia"):
                lowering_classes[language] = {
                    terminal: (
                        "native_semantic"
                        if self.terminals[terminal].get("isa") == "scalar"
                        else "semantic_scalar_fallback"
                    )
                    for terminal in terminals
                }
            families.append({
                "family": family,
                "source": self.sources[family],
                "rule_count": len(family_rules),
                "terminals": list(terminals),
                "graph_builder": "vladder.dataflow_ir:build_bounded_dataflow_graph",
                "cpp_emitter": "vladder.dataflow_lowering:emit_dataflow_cpp",
                "native_emitters": {
                    language: "vladder.dataflow_multilang:emit_dataflow_native"
                    for language in ("c", "cpp", "rust", "zig", "julia")
                },
                "native_lowering_classes": lowering_classes,
                "physical_distinction_policy": (
                    "native_physical still requires source/assembly deduplication; "
                    "native_semantic and semantic_scalar_fallback are not distinct physical claims"
                ),
                "proof_generator": "vladder.dataflow_proof:prove_dataflow_candidate",
                "differential_runner": "vladder.dataflow_lowering:run_dataflow_differential",
            })
        return {
            "schema_version": "vladder-bounded-dataflow-coverage-v1",
            "status": "pass",
            "grammar_version": self.version,
            "grammar_hash": self.hash,
            "family_count": len(families),
            "rule_count": len(self.rules),
            "terminal_count": len(self.terminals),
            "families": families,
        }

    def derive(self, contract: BoundedDataflowContract, target: str) -> DataflowDerivation:
        source = self.sources[contract.family]
        if target not in self.family_terminals(contract.family):
            raise ValueError(f"terminal {target!r} does not belong to {contract.family}")
        rules = () if target == source else tuple(
            item for item in self.rules if item.family == contract.family and item.target == target
        )
        if target != source and len(rules) != 1:
            raise ValueError(f"grammar does not uniquely derive {target} from {source}")
        source_graph = build_bounded_dataflow_graph(contract, source)
        target_graph = build_bounded_dataflow_graph(contract, target)
        proof = tuple(dict.fromkeys(value for rule in rules for value in rule.proof))
        payload = {
            "grammar_hash": self.hash,
            "contract": contract.to_dict(),
            "source_graph": source_graph.graph_hash,
            "target_graph": target_graph.graph_hash,
            "rules": [item.to_dict() for item in rules],
        }
        return DataflowDerivation(
            contract.family,
            source,
            target,
            rules,
            source_graph.graph_hash,
            target_graph.graph_hash,
            proof,
            canonical_hash(payload),
        )

    def search(self, contract: BoundedDataflowContract) -> tuple[DataflowDerivation, ...]:
        return tuple(self.derive(contract, target) for target in self.family_terminals(contract.family))


def load_bounded_dataflow_grammar(path: Path | None = None) -> BoundedDataflowGrammar:
    if path is None:
        resource = files("vladder").joinpath("grammars/bounded-dataflow-v1/grammar.json")
        return BoundedDataflowGrammar(json.loads(resource.read_text()), str(resource))
    return BoundedDataflowGrammar(json.loads(path.read_text()), str(path.resolve()))
