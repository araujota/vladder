from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from importlib.resources import files
from pathlib import Path
import time
from typing import Any

from .deep_ir import DeepKernelContract, DeepRealizationGraph, build_deep_realization_graph
from .language_adapter import canonical_hash


@dataclass(frozen=True)
class DeepRule:
    family: str
    id: str
    source: str
    target: str
    proof: tuple[str, ...]
    cost_signals: tuple[str, ...]
    complexity: str
    preconditions: tuple[str, ...]
    parameters: dict[str, Any]
    complexity_delta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeepDerivation:
    target: str
    rules: tuple[DeepRule, ...]
    source_graph_hash: str
    target_graph_hash: str
    status: str
    proof_obligations: tuple[str, ...]
    cost_signals: tuple[str, ...]
    derivation_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "rules": [rule.to_dict() for rule in self.rules],
            "source_graph_hash": self.source_graph_hash,
            "target_graph_hash": self.target_graph_hash,
            "status": self.status,
            "proof_obligations": list(self.proof_obligations),
            "cost_signals": list(self.cost_signals),
            "derivation_hash": self.derivation_hash,
        }


@dataclass(frozen=True)
class DeepSearchResult:
    grammar_version: str
    grammar_hash: str
    source: str
    explored_states: int
    saturated: bool
    derivations: tuple[DeepDerivation, ...]
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "vladder-deep-search-v1",
            "grammar_version": self.grammar_version,
            "grammar_hash": self.grammar_hash,
            "source": self.source,
            "explored_states": self.explored_states,
            "saturated": self.saturated,
            "classification": "bounded_optimal_local" if self.saturated else "best_verified_found",
            "derivations": [item.to_dict() for item in self.derivations],
            "elapsed_ms": self.elapsed_ms,
        }


class DeepGrammar:
    def __init__(self, payload: dict[str, Any], source: str) -> None:
        self.payload = payload
        self.source = source
        self.version = str(payload["version"])
        self.hash = canonical_hash(payload)
        self.rules = self._parse_rules(payload)
        self.terminals = {str(key): dict(value) for key, value in payload["terminal_realizations"].items()}
        self._validate()

    @staticmethod
    def _parse_rules(payload: dict[str, Any]) -> tuple[DeepRule, ...]:
        rules: list[DeepRule] = []
        for family in payload["families"]:
            for item in family["rules"]:
                target = str(item["to"])
                if target.startswith(("simd", "guarded")):
                    physical_parameters: dict[str, Any] = {"vector_bytes": 32, "lane_bits": 8}
                elif target.startswith("word"):
                    physical_parameters = {"word_bytes": 8, "lane_bits": 8}
                else:
                    physical_parameters = {"lane_bits": 8}
                complexity_name = str(item["complexity"])
                default_delta = dict((payload.get("complexity_models") or {}).get(complexity_name) or {})
                rules.append(DeepRule(
                    str(family["id"]),
                    str(item["id"]),
                    str(item["from"]),
                    target,
                    tuple(str(value) for value in item["proof"]),
                    tuple(str(value) for value in item["cost_signals"]),
                    complexity_name,
                    tuple(str(value) for value in item.get("preconditions", payload.get("default_preconditions", ()))),
                    {**physical_parameters, **dict(item.get("parameters") or {})},
                    {**default_delta, **dict(item.get("complexity_delta") or {})},
                ))
        return tuple(rules)

    def _validate(self) -> None:
        if self.payload.get("schema_version") != "vladder-deep-grammar-v1":
            raise ValueError("unsupported deep grammar schema")
        seen: set[str] = set()
        states = {"scalar"}
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"duplicate deep grammar rule: {rule.id}")
            seen.add(rule.id)
            if not rule.proof or not rule.cost_signals or not rule.preconditions or not rule.complexity_delta:
                raise ValueError(f"deep rule lacks proof or cost evidence: {rule.id}")
            states.add(rule.source)
            states.add(rule.target)
        unreachable = sorted(set(self.terminals) - states)
        if unreachable:
            raise ValueError(f"terminal realizations have no grammar states: {unreachable}")
        for name, terminal in self.terminals.items():
            if not terminal.get("emitter") or not terminal.get("languages"):
                raise ValueError(f"terminal realization lacks native emitters: {name}")

    def terminal(self, realization: str) -> dict[str, Any]:
        try:
            return dict(self.terminals[realization])
        except KeyError as error:
            raise KeyError(f"unknown terminal realization: {realization}") from error

    def coverage(self) -> dict[str, Any]:
        families: dict[str, dict[str, Any]] = {}
        for rule in self.rules:
            item = families.setdefault(rule.family, {"family": rule.family, "graph_rules": 0, "proof_rules": 0})
            item["graph_rules"] += 1
            item["proof_rules"] += int(bool(rule.proof))
        return {
            "schema_version": "vladder-deep-coverage-v1",
            "status": "pass",
            "grammar_version": self.version,
            "grammar_hash": self.hash,
            "family_count": len(families),
            "rule_count": len(self.rules),
            "terminal_realizations": {
                key: {
                    **value,
                    "graph_constructor": "vladder.deep_ir:build_deep_realization_graph",
                    "native_emitter": "vladder.deep_lowering:emit_deep_candidate",
                    "proof_generator": "vladder.deep_proof:prove_deep_candidate",
                    "benchmark_binding": "vladder.deep_benchmark:benchmark_deep_candidate",
                }
                for key, value in sorted(self.terminals.items())
            },
            "families": [families[key] for key in sorted(families)],
        }


def load_deep_grammar(path: Path | None = None) -> DeepGrammar:
    if path is None:
        resource = files("vladder").joinpath("grammars/deep-v2/grammar.json")
        payload = json.loads(resource.read_text())
        source = str(resource)
    else:
        payload = json.loads(path.read_text())
        source = str(path.resolve())
    return DeepGrammar(payload, source)


def search_deep_grammar(
    contract: DeepKernelContract,
    grammar: DeepGrammar | None = None,
    *,
    source: str = "scalar",
    targets: tuple[str, ...] | None = None,
    state_budget: int = 256,
    time_budget_ms: int = 1000,
) -> DeepSearchResult:
    grammar = grammar or load_deep_grammar()
    wanted = tuple(sorted(targets or tuple(grammar.terminals)))
    started = time.monotonic()
    queue: list[tuple[str, tuple[DeepRule, ...], frozenset[str]]] = [(source, (), frozenset({source}))]
    paths: dict[str, list[tuple[DeepRule, ...]]] = {source: [()]}
    path_identities = {(source, ())}
    explored_paths = 1
    saturated = True
    while queue:
        if explored_paths >= state_budget or (time.monotonic() - started) * 1000 >= time_budget_ms:
            saturated = False
            break
        state, path, seen_states = queue.pop(0)
        for rule in grammar.rules:
            if rule.source != state or rule.target in seen_states:
                continue
            next_path = path + (rule,)
            identity = (rule.target, tuple(item.id for item in next_path))
            if identity in path_identities:
                continue
            path_identities.add(identity)
            paths.setdefault(rule.target, []).append(next_path)
            queue.append((rule.target, next_path, seen_states | {rule.target}))
            explored_paths += 1
    source_graph = build_deep_realization_graph(contract, source, terminal=source in grammar.terminals)
    derivations: list[DeepDerivation] = []
    for target in wanted:
        if target not in paths or target not in grammar.terminals:
            continue
        target_graph = build_deep_realization_graph(contract, target, terminal=True)
        for rules in paths[target]:
            proof = tuple(dict.fromkeys(obligation for rule in rules for obligation in rule.proof))
            signals = tuple(dict.fromkeys(signal for rule in rules for signal in rule.cost_signals))
            payload = {
                "grammar_hash": grammar.hash,
                "source_graph_hash": source_graph.graph_hash,
                "target_graph_hash": target_graph.graph_hash,
                "rules": [rule.to_dict() for rule in rules],
            }
            derivations.append(DeepDerivation(
                target,
                rules,
                source_graph.graph_hash,
                target_graph.graph_hash,
                "derived",
                proof,
                signals,
                canonical_hash(payload),
            ))
    return DeepSearchResult(
        grammar.version,
        grammar.hash,
        source,
        explored_paths,
        saturated,
        tuple(sorted(derivations, key=lambda item: item.target)),
        (time.monotonic() - started) * 1000,
    )
