from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Any

from .c_lift import graph_ast, lift_c
from .candidates import Candidate
from .extractor import ExtractedFunction
from .flow import FlowGraph


@dataclass(frozen=True)
class GrammarRule:
    id: str
    input: str
    output: str
    preconditions: tuple[str, ...]
    proof: str
    cost: float


@dataclass(frozen=True)
class SearchResult:
    candidates: list[Candidate]
    status: str
    family: str
    grammar_file: str
    explored_states: int
    applied_rules: list[dict[str, Any]]
    node_budget: int
    time_budget_ms: int
    elapsed_ms: float

    def metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("candidates")
        return data


def search_candidates(fn: ExtractedFunction, graph: FlowGraph, cpu_flags: set[str], assume_no_alias: bool, grammar_dir: Path, node_budget: int = 64, time_budget_ms: int = 1000) -> SearchResult:
    start = time.monotonic()
    grammar_path = grammar_dir / f"{graph.family}.json"
    if not grammar_path.exists():
        grammar_path = grammar_dir / "pointwise_map.json"
    payload = json.loads(grammar_path.read_text())
    rules = [GrammarRule(r["id"], r["input"], r["output"], tuple(r["preconditions"]), r["proof"], float(r["cost"])) for r in payload["rules"]]
    facts = {
        **{k: bool(v) for k, v in graph.invariants.items()},
        "no_alias": assume_no_alias,
        "avx2": "avx2" in cpu_flags,
        "avx512f": "avx512f" in cpu_flags,
    }
    states: dict[str, tuple[float, list[str]]] = {"canonical": (1.0, [])}
    queue = ["canonical"]
    applied: list[dict[str, Any]] = []
    saturated = True
    while queue:
        if len(states) >= node_budget or (time.monotonic() - start) * 1000 >= time_budget_ms:
            saturated = False
            break
        current = queue.pop(0)
        for rule in rules:
            if rule.input != current or not all(facts.get(p, False) for p in rule.preconditions):
                continue
            provenance = states[current][1] + [rule.id]
            old = states.get(rule.output)
            if old is None or rule.cost < old[0]:
                states[rule.output] = (rule.cost, provenance)
                queue.append(rule.output)
                applied.append({"rule": rule.id, "from": current, "to": rule.output, "proof": rule.proof, "preconditions": list(rule.preconditions), "cost": rule.cost})

    original = "__attribute__((noinline))\n" + fn.renamed("transform_candidate")
    candidates = [
        Candidate("baseline_o3", original, tags=("original", "grammar"), proof="identity"),
        Candidate("compiler_funroll_loops", original, cflags=("-funroll-loops",), tags=("compiler-variant", "grammar"), proof="identity"),
        Candidate("compiler_no_vectorize", original, cflags=("-fno-vectorize", "-fno-slp-vectorize"), tags=("compiler-variant", "grammar"), proof="identity"),
    ]
    ast = graph_ast(graph)
    if ast is not None:
        for realization, (cost, provenance) in sorted(states.items(), key=lambda item: item[1][0]):
            if realization in {"canonical", "branch"}:
                continue
            if realization in {"avx2", "avx512"} and ast.canonical not in {"affine", "div_const", "saturating_projection"}:
                continue
            source = lift_c(ast, realization)
            vector = realization in {"avx2", "avx512"}
            cflags = ("-mavx2",) if realization == "avx2" else (("-mavx512f",) if realization == "avx512" else ())
            proof = _proof_schema(ast.canonical, realization)
            candidates.append(Candidate(f"grammar_{realization}_{ast.canonical}", source, cflags, vector, tuple(["grammar", realization, *provenance, f"estimated-cost:{cost}"]), proof))
    from .automatic import loop_hint_candidate

    structural = loop_hint_candidate(fn, graph, factor=4)
    if structural is not None and all(item.name != structural.name for item in candidates):
        candidates.append(structural)
    elapsed = (time.monotonic() - start) * 1000
    return SearchResult(candidates, "saturated_optimal" if saturated else "best_found", graph.family, str(grammar_path), len(states), applied, node_budget, time_budget_ms, elapsed)


def _proof_schema(canonical: str, realization: str) -> str:
    if canonical == "saturating_projection":
        return "clamp_branchless_vector" if realization in {"avx2", "avx512"} else "clamp_branchless"
    if canonical == "affine":
        return "affine_vector" if realization in {"avx2", "avx512"} else ("affine_unroll" if "unroll" in realization else "affine_identity")
    if canonical == "div_const":
        return "identity"
    return "graph_exact_unroll" if "unroll" in realization else "identity"
