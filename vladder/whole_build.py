from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
from typing import Any, Iterable

from .closure_bindings import cpp_effect_footprint, cpp_function_summary
from .cpp_regions import _entry_arguments, _resolve_entry_file, _semantic_arguments
from .cpp_semantics import analyze_ir_effects
from .language_adapter import canonical_hash
from .semantic_closure import (
    CallRelation,
    EffectFootprint,
    FunctionSummary,
    compose_system_graph,
    prove_system_graph,
)
from .toolchain import compiler_version, discover_toolchain, run


WHOLE_BUILD_SCHEMA = "vladder-whole-build-index-v1"
CROSS_TU_SCHEMA = "vladder-cross-tu-closure-v1"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes()) if path.exists() else ""


def _resolve_output(entry: dict[str, Any], arguments: list[str], directory: Path) -> Path | None:
    output = entry.get("output")
    if isinstance(output, str) and output:
        path = Path(output)
        return (path if path.is_absolute() else directory / path).resolve()
    for index, argument in enumerate(arguments):
        if argument == "-o" and index + 1 < len(arguments):
            path = Path(arguments[index + 1])
            return (path if path.is_absolute() else directory / path).resolve()
        if argument.startswith("-o") and len(argument) > 2:
            path = Path(argument[2:])
            return (path if path.is_absolute() else directory / path).resolve()
    return None


@dataclass(frozen=True)
class BuildTranslationUnit:
    id: str
    index: int
    directory: str
    source: str
    output: str | None
    arguments: tuple[str, ...]
    semantic_arguments: tuple[str, ...]
    command_sha256: str
    source_sha256: str
    object_sha256: str
    definitions: tuple[str, ...]
    references: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WholeBuildIndex:
    """Deterministic build-wide symbol identity without whole-program search expansion."""

    def __init__(self, compile_commands: str, units: Iterable[BuildTranslationUnit]) -> None:
        self.compile_commands = str(Path(compile_commands).resolve())
        self.units = tuple(sorted(units, key=lambda item: item.id))
        self.by_id = {item.id: item for item in self.units}
        self.definitions: dict[str, list[str]] = {}
        self.references: dict[str, list[str]] = {}
        for unit in self.units:
            for symbol in unit.definitions:
                self.definitions.setdefault(symbol, []).append(unit.id)
            for symbol in unit.references:
                self.references.setdefault(symbol, []).append(unit.id)
        for values in (*self.definitions.values(), *self.references.values()):
            values.sort()

    @staticmethod
    def _nm_symbols(output: Path) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        nm = shutil.which("llvm-nm-20") or shutil.which("llvm-nm") or shutil.which("nm")
        if not nm:
            return (), (), ("llvm-nm or nm is unavailable",)
        result = run([nm, "--format=posix", str(output)], timeout=60)
        if result.returncode != 0:
            return (), (), (f"symbol scan failed: {(result.stdout + result.stderr)[-500:]}",)
        definitions: set[str] = set()
        references: set[str] = set()
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            symbol, kind = fields[0], fields[1]
            if kind.upper() == "U":
                references.add(symbol)
            elif kind.isupper() or kind in {"W", "V"}:
                definitions.add(symbol)
        return tuple(sorted(definitions)), tuple(sorted(references)), ()

    @classmethod
    def from_compilation_database(cls, path: Path) -> WholeBuildIndex:
        database = path.resolve()
        if database.is_dir():
            database = database / "compile_commands.json"
        raw = json.loads(database.read_text())
        if not isinstance(raw, list):
            raise ValueError("compile_commands.json must contain an array")
        units: list[BuildTranslationUnit] = []
        seen: dict[str, int] = {}
        for index, entry in enumerate(raw):
            if not isinstance(entry, dict):
                continue
            directory = Path(str(entry.get("directory", "."))).resolve()
            source = _resolve_entry_file(entry)
            arguments = _entry_arguments(entry)
            output = _resolve_output(entry, arguments, directory)
            semantic = _semantic_arguments(arguments, source, directory)
            identity_payload = {
                "directory": str(directory),
                "source": str(source),
                "arguments": arguments,
                "output": str(output) if output else None,
            }
            command_hash = canonical_hash(identity_payload)
            base = f"tu:{command_hash[:20]}"
            duplicate = seen.get(base, 0)
            seen[base] = duplicate + 1
            identifier = base if duplicate == 0 else f"{base}:{duplicate}"
            diagnostics: list[str] = []
            definitions: tuple[str, ...] = ()
            references: tuple[str, ...] = ()
            if output and output.exists():
                definitions, references, symbol_diagnostics = cls._nm_symbols(output)
                diagnostics.extend(symbol_diagnostics)
            else:
                diagnostics.append("output object is unavailable; symbol identity requires an existing build")
            units.append(BuildTranslationUnit(
                identifier,
                index,
                str(directory),
                str(source),
                str(output) if output else None,
                tuple(arguments),
                tuple(semantic),
                command_hash,
                _sha256_file(source),
                _sha256_file(output) if output else "",
                definitions,
                references,
                tuple(diagnostics),
            ))
        return cls(str(database), units)

    def resolve_definition(self, symbol: str) -> dict[str, Any]:
        units = tuple(self.definitions.get(symbol, ()))
        if len(units) == 1:
            return {"symbol": symbol, "status": "unique", "translation_units": list(units), "selected": units[0]}
        if not units:
            return {"symbol": symbol, "status": "unresolved", "translation_units": [], "selected": None}
        return {"symbol": symbol, "status": "ambiguous_odr", "translation_units": list(units), "selected": None}

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": WHOLE_BUILD_SCHEMA,
            "compile_commands": self.compile_commands,
            "translation_units": [item.to_dict() for item in self.units],
            "definitions": {key: value for key, value in sorted(self.definitions.items())},
            "references": {key: value for key, value in sorted(self.references.items())},
            "counts": {
                "translation_units": len(self.units),
                "defined_symbols": len(self.definitions),
                "referenced_symbols": len(self.references),
                "ambiguous_definitions": sum(len(value) > 1 for value in self.definitions.values()),
                "units_without_objects": sum(not item.object_sha256 for item in self.units),
            },
        }
        return {**payload, "index_sha256": canonical_hash(payload)}

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return path

    @classmethod
    def read(cls, path: Path) -> WholeBuildIndex:
        raw = json.loads(path.read_text())
        units = [BuildTranslationUnit(
            id=item["id"], index=int(item["index"]), directory=item["directory"], source=item["source"],
            output=item.get("output"), arguments=tuple(item.get("arguments", ())),
            semantic_arguments=tuple(item.get("semantic_arguments", ())), command_sha256=item["command_sha256"],
            source_sha256=item.get("source_sha256", ""), object_sha256=item.get("object_sha256", ""),
            definitions=tuple(item.get("definitions", ())), references=tuple(item.get("references", ())),
            diagnostics=tuple(item.get("diagnostics", ())),
        ) for item in raw.get("translation_units", [])]
        return cls(raw["compile_commands"], units)


def _defined_ir_symbols(module_text: str) -> tuple[str, ...]:
    return tuple(sorted(set(
        match.group(1) or match.group(2)
        for match in re.finditer(r'^define\s+[^\n]*@(?:"([^"]+)"|([-A-Za-z$._0-9]+))\(', module_text, re.MULTILINE)
    )))


def _ir_function_bodies(module_text: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    pattern = re.compile(r'^define\s+[^\n]*@(?:"([^"]+)"|([-A-Za-z$._0-9]+))\([^\n]*\).*\{\s*$', re.MULTILINE)
    for match in pattern.finditer(module_text):
        symbol = match.group(1) or match.group(2)
        opening = module_text.find("{", match.start(), match.end())
        depth = 0
        end = None
        for index in range(opening, len(module_text)):
            if module_text[index] == "{":
                depth += 1
            elif module_text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is not None:
            bodies[symbol] = module_text[match.start():end]
    return bodies


def _analysis_shell(module_text: str, body: str) -> str:
    declarations = "\n".join(re.findall(r'^declare\s+.*$', module_text, re.MULTILINE))
    attributes = "\n".join(re.findall(r'^attributes\s+#\d+\s*=\s*\{.*$', module_text, re.MULTILINE))
    return f"{body}\n{declarations}\n{attributes}\n"


def _direct_targets(body: str) -> tuple[str, ...]:
    return tuple(sorted(set(
        match.group(1) or match.group(2)
        for match in re.finditer(r'\b(?:call|invoke)\b[^\n]*@(?:"([^"]+)"|([-A-Za-z$._0-9]+))\s*\(', body)
    )))


class CrossTUSummaryDatabase:
    """Persistent demand-driven LLVM summaries bound to a WholeBuildIndex."""

    def __init__(self, index: WholeBuildIndex, root: Path) -> None:
        self.index = index
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._summaries: dict[str, FunctionSummary] = {}
        self._symbol_units: dict[str, str] = {}
        self._module_cache: dict[str, tuple[str, dict[str, str]]] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for path in sorted(self.root.glob("tu-*/summaries.json")):
            try:
                value = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if value.get("index_sha256") != self.index.to_dict()["index_sha256"]:
                continue
            for raw in value.get("summaries", []):
                summary = FunctionSummary.from_dict(raw)
                native = summary.id.split("::", 1)[1]
                self._summaries[native] = summary
                self._symbol_units[native] = str(value.get("translation_unit"))

    def _unit_directory(self, unit: BuildTranslationUnit) -> Path:
        return self.root / f"tu-{unit.command_sha256[:20]}"

    def _module(self, unit: BuildTranslationUnit) -> tuple[str, dict[str, str], Path, str, str]:
        output = self._unit_directory(unit)
        output.mkdir(parents=True, exist_ok=True)
        ir_path = output / "analysis.ll"
        tc = discover_toolchain()
        if not ir_path.exists():
            flags = [
                *unit.semantic_arguments,
                "-O1", "-fno-inline", "-fno-vectorize", "-fno-slp-vectorize", "-fno-unroll-loops",
                "-S", "-emit-llvm", unit.source, "-o", str(ir_path),
            ]
            result = run([tc.compiler, *flags], cwd=Path(unit.directory), timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"cross-TU IR emission failed for {unit.source}: {(result.stdout + result.stderr)[-2000:]}")
        cached = self._module_cache.get(unit.id)
        if cached is None:
            module_text = ir_path.read_text(errors="replace")
            cached = (module_text, _ir_function_bodies(module_text))
            self._module_cache[unit.id] = cached
        return cached[0], cached[1], ir_path, tc.compiler, compiler_version(tc.compiler)

    def caller_symbols(self, unit_id: str, target: str) -> tuple[str, ...]:
        unit = self.index.by_id[unit_id]
        _, bodies, _, _, _ = self._module(unit)
        return tuple(sorted(symbol for symbol, body in bodies.items() if target in _direct_targets(body)))

    def materialize_translation_unit(
        self,
        unit_id: str,
        symbols: Iterable[str] | None = None,
    ) -> tuple[FunctionSummary, ...]:
        unit = self.index.by_id[unit_id]
        output = self._unit_directory(unit)
        module_text, bodies, ir_path, compiler, compiler_identity = self._module(unit)
        requested = set(symbols or ())
        if not requested:
            requested = set(unit.definitions) & set(bodies)
        existing = [
            summary for symbol, summary in self._summaries.items()
            if self._symbol_units.get(symbol) == unit_id and symbol in requested
        ]
        missing = requested - {item.id.split("::", 1)[1] for item in existing}
        if not missing:
            return tuple(sorted(existing, key=lambda item: item.id))
        summaries: list[FunctionSummary] = []
        module_symbols = set(bodies)
        for symbol in sorted(missing & module_symbols):
            try:
                effects = analyze_ir_effects(module_text, symbol)
            except ValueError:
                continue
            resolved_project_externals = {
                target for target in effects.get("external_calls", ())
                if self.index.resolve_definition(target)["status"] == "unique" or target in module_symbols
            }
            local_effects = dict(effects)
            local_effects["external_calls"] = sorted(set(effects.get("external_calls", ())) - resolved_project_externals)
            summary = cpp_function_summary(
                symbol,
                compiler_identity,
                local_effects,
                semantic_capture="cross-tu-analysis-ir",
            )
            refined_calls: list[CallRelation] = []
            for relation in summary.calls:
                native = str(relation.provenance.get("native_construct", relation.callsite))
                resolution = self.index.resolve_definition(native)
                same_tu = native in module_symbols
                if relation.kind in {"opaque", "definition"} and same_tu:
                    internal = effects.get("internal_call_summaries", {}).get(native, {})
                    relation_effects = relation.effects
                    if relation.kind == "opaque":
                        relation_effects = cpp_effect_footprint({
                            "memory_effect": internal.get("memory_effect", "unknown"),
                            "nounwind": internal.get("nounwind", False),
                        })
                    refined_calls.append(CallRelation(
                        relation.id,
                        relation.caller,
                        (),
                        "intrinsic",
                        relation.callsite,
                        relation_effects,
                        relation.argument_ownership,
                        relation.result_channels,
                        relation.preconditions,
                        relation.postconditions,
                        "definition-hash",
                        "call-preserving-only",
                        provenance={
                            **relation.provenance,
                            "resolution": "same-translation-unit-transitive-summary",
                            "target_translation_unit": unit_id,
                            "next_action": "retain the call or separately materialize a local functional proof",
                        },
                    ))
                elif relation.kind == "opaque" and resolution["status"] == "unique":
                    refined_calls.append(CallRelation(
                        relation.id,
                        relation.caller,
                        (f"cpp::{native}",),
                        "definition",
                        relation.callsite,
                        EffectFootprint(),
                        relation.argument_ownership,
                        relation.result_channels,
                        relation.preconditions,
                        relation.postconditions,
                        "definition-hash",
                        "call-preserving-only",
                        provenance={
                            **relation.provenance,
                            "resolution": "whole-build-index",
                            "target_translation_unit": resolution["selected"],
                            "index_sha256": self.index.to_dict()["index_sha256"],
                            "next_action": "materialize the target summary or preserve the call boundary",
                        },
                    ))
                else:
                    refined_calls.append(relation)
            summary = replace(
                summary,
                local_effects=cpp_effect_footprint(local_effects),
                calls=tuple(refined_calls),
                contracts={
                    **summary.contracts,
                    "translation_unit": unit_id,
                    "source": unit.source,
                    "source_sha256": unit.source_sha256,
                    "command_sha256": unit.command_sha256,
                    "object_sha256": unit.object_sha256,
                    "analysis_ir_sha256": _sha256_file(ir_path),
                },
            )
            summaries.append(summary)
            self._summaries[symbol] = summary
            self._symbol_units[symbol] = unit_id
        payload = {
            "schema_version": CROSS_TU_SCHEMA,
            "index_sha256": self.index.to_dict()["index_sha256"],
            "translation_unit": unit_id,
            "source": unit.source,
            "source_sha256": unit.source_sha256,
            "command_sha256": unit.command_sha256,
            "compiler": compiler,
            "compiler_identity": compiler_identity,
            "analysis_ir": str(ir_path),
            "analysis_ir_sha256": _sha256_file(ir_path),
            "summaries": [
                item.to_dict() for item in sorted(
                    [summary for native, summary in self._summaries.items() if self._symbol_units.get(native) == unit_id],
                    key=lambda item: item.id,
                )
            ],
        }
        (output / "summaries.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return tuple(sorted((*existing, *summaries), key=lambda item: item.id))

    def summary(self, symbol: str) -> FunctionSummary | None:
        if symbol in self._summaries:
            return self._summaries[symbol]
        resolution = self.index.resolve_definition(symbol)
        if resolution["status"] != "unique":
            return None
        self.materialize_translation_unit(str(resolution["selected"]), (symbol,))
        return self._summaries.get(symbol)

    def materialized_summaries(self) -> tuple[FunctionSummary, ...]:
        return tuple(sorted(self._summaries.values(), key=lambda item: item.id))


class BidirectionalProgramSlice:
    def __init__(
        self,
        index: WholeBuildIndex,
        summaries: CrossTUSummaryDatabase,
        *,
        max_upstream: int = 1,
        max_downstream: int = 3,
        max_nodes: int = 128,
    ) -> None:
        self.index = index
        self.summaries = summaries
        self.max_upstream = max(0, max_upstream)
        self.max_downstream = max(0, max_downstream)
        self.max_nodes = max(1, max_nodes)

    @staticmethod
    def _native(identity: str) -> str:
        return identity.split("::", 1)[1] if "::" in identity else identity

    def build(self, seeds: Iterable[str]) -> dict[str, Any]:
        seed_symbols = tuple(sorted(set(seeds)))
        included: dict[str, FunctionSummary] = {}
        edge_rows: dict[tuple[str, str], dict[str, Any]] = {}
        boundaries: list[dict[str, Any]] = []
        downstream_queue = [(symbol, 0) for symbol in seed_symbols]
        while downstream_queue and len(included) < self.max_nodes:
            symbol, depth = downstream_queue.pop(0)
            summary = self.summaries.summary(symbol)
            if summary is None:
                boundaries.append({"symbol": symbol, "direction": "downstream", **self.index.resolve_definition(symbol)})
                continue
            included[summary.id] = summary
            if depth >= self.max_downstream:
                continue
            for relation in summary.calls:
                if relation.kind in {"opaque", "protocol"}:
                    boundaries.append({
                        "symbol": relation.callsite,
                        "caller": summary.id,
                        "direction": "downstream",
                        "status": relation.kind,
                        "reason": relation.provenance.get("missing_contract", "explicit protocol or call-preserving boundary"),
                    })
                if relation.kind != "definition":
                    continue
                for target in relation.targets:
                    native = self._native(target)
                    edge_rows[(summary.id, target)] = {
                        "source": summary.id,
                        "destination": target,
                        "direction": "downstream",
                        "precision": "function-direct-call",
                        "call_relation": relation.id,
                    }
                    if target not in included:
                        downstream_queue.append((native, depth + 1))

        frontier = set(seed_symbols)
        for depth in range(self.max_upstream):
            next_frontier: set[str] = set()
            for target_symbol in sorted(frontier):
                candidate_units = self.index.references.get(target_symbol, ())
                for unit_id in candidate_units:
                    if len(included) >= self.max_nodes:
                        break
                    caller_symbols = self.summaries.caller_symbols(unit_id, target_symbol)
                    for summary in self.summaries.materialize_translation_unit(unit_id, caller_symbols):
                        matching = [
                            relation for relation in summary.calls
                            if f"cpp::{target_symbol}" in relation.targets
                        ]
                        if not matching:
                            continue
                        included[summary.id] = summary
                        native_caller = self._native(summary.id)
                        next_frontier.add(native_caller)
                        edge_rows[(summary.id, f"cpp::{target_symbol}")] = {
                            "source": summary.id,
                            "destination": f"cpp::{target_symbol}",
                            "direction": "upstream",
                            "precision": "function-direct-call",
                            "call_relations": [item.id for item in matching],
                            "upstream_depth": depth + 1,
                        }
            frontier = next_frontier

        payload = {
            "schema_version": CROSS_TU_SCHEMA,
            "seeds": list(seed_symbols),
            "budgets": {
                "max_upstream": self.max_upstream,
                "max_downstream": self.max_downstream,
                "max_nodes": self.max_nodes,
            },
            "functions": [item.to_dict() for item in sorted(included.values(), key=lambda item: item.id)],
            "edges": sorted(edge_rows.values(), key=lambda item: (item["source"], item["destination"])),
            "boundaries": sorted(boundaries, key=lambda item: (str(item.get("caller", "")), str(item.get("symbol", "")))),
            "truncated": len(included) >= self.max_nodes or bool(downstream_queue),
            "candidate_dimensions_added": 0,
        }
        return {**payload, "slice_sha256": canonical_hash(payload)}


class OwnershipClosureGraph:
    def build(self, slice_graph: dict[str, Any]) -> dict[str, Any]:
        resources: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        boundaries: list[dict[str, Any]] = []
        for function in slice_graph.get("functions", []):
            identifier = str(function["id"])
            effects = function.get("transitive_effects", function.get("local_effects", {}))
            flags = set(effects.get("flags", ()))
            for region in effects.get("reads", ()):
                resource = f"memory:{region}"
                resources.setdefault(resource, {"id": resource, "kind": "memory-region"})
                edges.append({"source": identifier, "destination": resource, "kind": "borrow-read"})
            for region in effects.get("writes", ()):
                resource = f"memory:{region}"
                resources.setdefault(resource, {"id": resource, "kind": "memory-region"})
                edges.append({"source": identifier, "destination": resource, "kind": "mutate"})
            if "allocate" in flags or "deallocate" in flags:
                resource = f"owned:{identifier}"
                resources.setdefault(resource, {"id": resource, "kind": "owned-allocation"})
                if "allocate" in flags:
                    edges.append({"source": identifier, "destination": resource, "kind": "construct"})
                if "deallocate" in flags:
                    edges.append({"source": identifier, "destination": resource, "kind": "retire"})
                if "allocate" in flags and "deallocate" not in flags:
                    boundaries.append({
                        "resource": resource,
                        "function": identifier,
                        "kind": "ownership-transfer-or-leak-boundary",
                        "required_contract": "result ownership transfer or retirement relation",
                    })
            for flag, kind in (("publish", "publish"), ("invalidate", "invalidate"), ("synchronize", "synchronize")):
                if flag in flags:
                    resource = "memory:shared-state"
                    resources.setdefault(resource, {"id": resource, "kind": "shared-state"})
                    edges.append({"source": identifier, "destination": resource, "kind": kind})
            if effects.get("unknown"):
                boundaries.append({
                    "resource": "unknown-authority",
                    "function": identifier,
                    "kind": "unknown-effect-boundary",
                    "required_contract": "finite ownership/effect protocol",
                })
        payload = {
            "schema_version": CROSS_TU_SCHEMA,
            "resources": [resources[key] for key in sorted(resources)],
            "edges": sorted(edges, key=lambda item: (item["source"], item["destination"], item["kind"])),
            "boundaries": sorted(boundaries, key=lambda item: (item["function"], item["kind"])),
            "closure": "closed" if not boundaries else "partial_with_explicit_boundaries",
        }
        return {**payload, "ownership_sha256": canonical_hash(payload)}


class SummaryCompositionProof:
    def __init__(self, index: WholeBuildIndex) -> None:
        self.index = index

    @staticmethod
    def _finite_obligation(z3: Any, identifier: str, condition: bool, output: Path) -> dict[str, Any]:
        solver = z3.Solver()
        solver.add(z3.BoolVal(not condition))
        status = solver.check()
        path = output / f"{re.sub(r'[^A-Za-z0-9_.-]+', '-', identifier)[:120]}.smt2"
        path.write_text(solver.to_smt2())
        return {
            "id": identifier,
            "status": "PASS" if status == z3.unsat else "FAIL",
            "method": "Z3 finite closure invariant",
            "artifact": str(path),
        }

    def prove(self, slice_graph: dict[str, Any], ownership: dict[str, Any], output: Path) -> dict[str, Any]:
        output.mkdir(parents=True, exist_ok=True)
        functions = tuple(FunctionSummary.from_dict(item) for item in slice_graph.get("functions", ()))
        system = compose_system_graph("cross-tu-slice", functions)
        base = prove_system_graph(system, output / "effect-closure")
        try:
            import z3
        except ImportError:
            return {
                "schema_version": CROSS_TU_SCHEMA,
                "status": "UNAVAILABLE",
                "method": "Z3",
                "system_graph": system,
                "base_proof": base,
                "obligations": [],
            }
        obligations: list[dict[str, Any]] = []
        ids = {item["id"] for item in slice_graph.get("functions", ())}
        for edge in slice_graph.get("edges", ()):
            target = str(edge["destination"])
            native = target.split("::", 1)[1] if "::" in target else target
            resolution = self.index.resolve_definition(native)
            condition = target in ids and resolution["status"] == "unique"
            obligations.append(self._finite_obligation(z3, f"definition:{native}", condition, output))
        for function in slice_graph.get("functions", ()):
            contracts = function.get("contracts", {})
            bound = all(contracts.get(key) for key in ("source_sha256", "command_sha256", "analysis_ir_sha256"))
            obligations.append(self._finite_obligation(z3, f"provenance:{function['id']}", bound, output))
        all_edges_disposed = all(
            edge.get("destination") in ids for edge in slice_graph.get("edges", ())
        ) and all(boundary.get("status") or boundary.get("kind") for boundary in slice_graph.get("boundaries", ()))
        obligations.append(self._finite_obligation(z3, "total-edge-disposition", all_edges_disposed, output))
        ownership_disposed = all(boundary.get("required_contract") for boundary in ownership.get("boundaries", ()))
        obligations.append(self._finite_obligation(z3, "ownership-disposition", ownership_disposed, output))
        obligations.append(self._finite_obligation(
            z3,
            "search-space-separation",
            int(slice_graph.get("candidate_dimensions_added", -1)) == 0,
            output,
        ))
        status = "PASS" if base.get("status") == "PASS" and all(item["status"] == "PASS" for item in obligations) else "FAIL"
        return {
            "schema_version": CROSS_TU_SCHEMA,
            "status": status,
            "method": "Z3 + deterministic cross-TU summary composition",
            "system_graph": system,
            "base_proof": base,
            "obligations": obligations,
            "claim_boundary": (
                "definition identity, provenance, transitive effects, ownership disposition, and bounded slice closure; "
                "not functional equivalence across calls or external protocol implementations"
            ),
        }


def run_cross_tu_closure(
    compile_commands: Path,
    seeds: Iterable[str],
    output: Path,
    *,
    max_upstream: int = 1,
    max_downstream: int = 3,
    max_nodes: int = 128,
) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    index = WholeBuildIndex.from_compilation_database(compile_commands)
    index.write(output / "whole-build-index.json")
    database = CrossTUSummaryDatabase(index, output / "summary-database")
    slice_graph = BidirectionalProgramSlice(
        index,
        database,
        max_upstream=max_upstream,
        max_downstream=max_downstream,
        max_nodes=max_nodes,
    ).build(seeds)
    ownership = OwnershipClosureGraph().build(slice_graph)
    proof = SummaryCompositionProof(index).prove(slice_graph, ownership, output / "proofs")
    report = {
        "schema_version": CROSS_TU_SCHEMA,
        "status": "pass" if proof["status"] == "PASS" else "proof_failed",
        "index": index.to_dict(),
        "slice": slice_graph,
        "ownership": ownership,
        "proof": proof,
        "meaningful_semantic_coverage": bool(slice_graph["functions"]),
        "candidate_generation_performed": False,
        "candidate_dimensions_added": 0,
        "source_changes_performed": False,
        "next_action": (
            "run attributed computational grammars inside closed slice regions; preserve explicit boundaries"
        ),
    }
    (output / "bidirectional-slice.json").write_text(json.dumps(slice_graph, indent=2, sort_keys=True) + "\n")
    (output / "ownership-closure.json").write_text(json.dumps(ownership, indent=2, sort_keys=True) + "\n")
    (output / "cross-tu-closure-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
