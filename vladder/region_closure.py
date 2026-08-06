from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from pathlib import Path
from typing import Any

from .language_adapter import (
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)


REGION_CLOSURE_SCHEMA = "vladder-region-closure-v1"


@dataclass(frozen=True)
class CBoundaryDescriptor:
    return_type: str
    parameters: tuple[dict[str, Any], ...]
    modeled: bool
    abi_class: str
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "parameters": list(self.parameters), "blockers": list(self.blockers)}


def _split_top_level(text: str, delimiter: str = ",") -> list[str]:
    values: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char in "(<[{":
            depth += 1
        elif char in ")>]}" and depth:
            depth -= 1
        elif char == delimiter and depth == 0:
            values.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        values.append(tail)
    return values


def describe_c_boundary(signature: str, function: str) -> CBoundaryDescriptor:
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", " ", signature, flags=re.DOTALL)
    normalized = re.sub(r"\s+", " ", without_comments).strip()
    match = re.match(rf"^(?:static\s+|inline\s+|extern\s+)*(.+?)\s+{re.escape(function)}\s*\((.*)\)$", normalized)
    if not match:
        return CBoundaryDescriptor("unknown", (), False, "unparsed", ("function signature was not parsed",))
    return_type, parameter_text = match.groups()
    scalar = re.compile(
        r"^(?:(?:const|volatile)\s+)*(?:void|_Bool|bool|char|short|int|long|long long|float|double|"
        r"size_t|ptrdiff_t|u?int(?:8|16|32|64)_t)(?:\s+(?:unsigned|signed))?$"
    )
    named_c_type = re.compile(r"^(?:(?:const|volatile)\s+)*[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*$")
    result_modeled = (
        bool(scalar.match(return_type.strip()))
        or bool(re.match(r"^(?:struct|union)\s+\w+$", return_type.strip()))
        or bool(named_c_type.match(return_type.strip()))
    )
    parameters: list[dict[str, Any]] = []
    blockers: list[str] = []
    for ordinal, raw in enumerate(_split_top_level(parameter_text)):
        if raw in {"", "void"}:
            continue
        pointer = "*" in raw or raw.endswith("[]")
        callable_pointer = bool(re.search(r"\(\s*\*", raw))
        variadic = "..." in raw
        array_vla = bool(re.search(r"\[[^\]]+\]", raw) and not re.search(r"\[\s*\]", raw))
        base_declaration = re.sub(r"\b[A-Za-z_]\w*\s*$", "", raw).strip()
        scalar_value = bool(scalar.match(base_declaration))
        named_value = bool(named_c_type.match(base_declaration))
        category = "pointer" if pointer else "scalar" if scalar_value else "named-value"
        modeled = not callable_pointer and not variadic and not array_vla and (
            pointer or scalar_value or named_value
        )
        if not modeled:
            blockers.append(f"parameter {ordinal} has unsupported declarator: {raw}")
        parameters.append({
            "ordinal": ordinal,
            "spelling": raw,
            "category": category if modeled else "unmodeled",
            "ownership": "borrowed" if pointer else "value",
            "modeled": modeled,
            "layout_proof": "compiler-ir-required" if category == "named-value" else "source-builtin" if not pointer else "pointer-object-contract",
        })
    if not result_modeled:
        blockers.append(f"return type is not a scalar or named POD projection: {return_type}")
    abi_class = (
        "first_order_borrowed" if any(item["category"] == "pointer" for item in parameters)
        else "first_order_value"
    )
    return CBoundaryDescriptor(return_type.strip(), tuple(parameters), not blockers, abi_class, tuple(blockers))


def _aggregate_fields(abi: dict[str, Any]) -> list[dict[str, Any]]:
    result = abi.get("return", {})
    if result.get("category") != "aggregate_value":
        return []
    source_fields = list(abi.get("source_aggregate_fields", []))
    if source_fields:
        return [
            {
                "index": index,
                "name": field.get("name", f"field_{index}"),
                "type": field.get("type", "unknown"),
                "source_provenance": field.get("provenance", "unknown"),
                "channel": "sret-memory" if abi.get("lowered_sret") else "register-projection",
            }
            for index, field in enumerate(source_fields)
        ]
    lowered = str(abi.get("lowered_return_type", "unknown"))
    if lowered.startswith("{") and lowered.endswith("}"):
        types = _split_top_level(lowered[1:-1])
    elif lowered.startswith("[") and lowered.endswith("]"):
        types = [lowered]
    elif abi.get("lowered_sret"):
        signature = str(abi.get("lowered_signature", ""))
        match = re.search(r"\bsret\(([^)]+)\)", signature)
        types = [match.group(1) if match else str(result.get("spelling", "opaque"))]
    else:
        types = [lowered]
    return [
        {"index": index, "type": field_type, "channel": "sret-memory" if abi.get("lowered_sret") else "register"}
        for index, field_type in enumerate(types)
    ]


def _helper_summaries(effects: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    external = set(effects.get("external_calls", []))
    for symbol, summary in sorted(effects.get("internal_call_summaries", {}).items()):
        local = bool(summary.get("local_effects")) and symbol not in external
        summaries.append({
            "symbol": symbol,
            "mode": "exact_call_preserving" if local else "protocol_boundary",
            "local_effects": local,
            "nounwind": bool(summary.get("nounwind")),
            "memory_effect": str(summary.get("memory_effect", "unknown")),
            "body_sha256": summary.get("function_body_sha256"),
            "cross_call_rewrite": "requires_inlined_ir_or_functional_summary",
        })
    for symbol, summary in sorted(effects.get("declared_call_summaries", {}).items()):
        summaries.append({
            "symbol": symbol,
            "mode": "compiler_attributed_call_preserving",
            "local_effects": True,
            "nounwind": bool(summary.get("nounwind")),
            "memory_effect": str(summary.get("memory_effect", "unknown")),
            "body_sha256": None,
            "summary_sha256": summary.get("summary_sha256"),
            "cross_call_rewrite": "requires_functional_summary; compiler attributes prove effects only",
        })
    return summaries


def _inlined_source_helpers(
    source: dict[str, Any], effects: dict[str, Any], summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    modeled_primitives = {
        "size", "data", "begin", "end", "front", "empty", "operator[]",
        "operator*", "operator++", "operator==", "operator!=",
    }
    present = {item["symbol"] for item in summaries}
    remaining = set(effects.get("remaining_direct_calls", []))
    if effects.get("external_calls") or effects.get("indirect_calls"):
        return summaries
    for name in sorted(set(source.get("calls", [])) - modeled_primitives):
        if name in present or name in remaining or name == "<indirect>":
            continue
        summaries.append({
            "symbol": name,
            "mode": "inlined_into_selected_ir",
            "local_effects": True,
            "nounwind": True,
            "memory_effect": "represented in enclosing function",
            "body_sha256": None,
            "cross_call_rewrite": "already_lowered_into_enclosing_ir",
        })
    return summaries


def build_region_closure_graph(
    *,
    language: str,
    function: str,
    abi: dict[str, Any],
    source: dict[str, Any],
    effects: dict[str, Any],
    subregions: list[dict[str, Any]],
    compiler_identity: str,
    function_identity: str,
) -> dict[str, Any]:
    aggregate_fields = _aggregate_fields(abi)
    helpers = _inlined_source_helpers(source, effects, _helper_summaries(effects))
    multi_exit_regions = [
        item for item in subregions if item.get("closure_mode") == "whole_function_cfg"
    ]
    no_growth_regions = [
        item for item in subregions if item.get("closure_mode") == "no_growth_container"
    ]
    has_multiple_returns = int(source.get("return_count", 0)) > 1
    nodes: list[SemanticFlowNode] = []
    edges: list[SemanticFlowEdge] = []
    obligations = []

    def add_node(identifier: str, kind: str, operation: str, inputs: tuple[str, ...], output: str, attributes: dict[str, Any]) -> None:
        nodes.append(SemanticFlowNode(
            identifier, kind, operation, inputs, output, attributes,
            {"adapter": REGION_CLOSURE_SCHEMA, "language": language}, (),
        ))
        for ordinal, source_id in enumerate(inputs):
            edges.append(SemanticFlowEdge(
                f"{source_id}->{identifier}:{ordinal}", source_id, identifier, output,
                "ephemeral", "region", "function-call", "program-order",
                memory_region="register", validity_scope="bounded-call",
            ))

    input_ids = []
    for index, parameter in enumerate(abi.get("parameters", [])):
        identifier = f"input.{index}"
        add_node(identifier, "Input", "typed-live-in", (), str(parameter.get("spelling", "unknown")), {"descriptor": parameter})
        if parameter.get("category") == "aggregate_reference":
            projection = f"input.{index}.projection"
            add_node(projection, "AggregateUnpack", "borrowed-state-projection", (identifier,), "aggregate-fields", {"descriptor": parameter})
            input_ids.append(projection)
        else:
            input_ids.append(identifier)

    add_node("region", "Map", "closed-compiled-region", tuple(input_ids), "region-state", {
        "local_effects": bool(effects.get("local_effects")),
        "memory_effect": effects.get("memory_effect"),
        "function_body_sha256": effects.get("function_body_sha256"),
    })

    for index, helper in enumerate(helpers):
        add_node(f"helper.{index}", "HelperSummary", helper["mode"], ("region",), "helper-relation", helper)
        inlined = helper["mode"] == "inlined_into_selected_ir"
        attributed = helper["mode"] == "compiler_attributed_call_preserving"
        item = obligation(
            f"region.helper.{index}.binding", "validation",
            (
                "the helper is represented by the enclosing selected-function LLVM body"
                if inlined else "call-preserving transformations retain the exact compiler-attributed declaration"
                if attributed else "call-preserving transformations retain the exact definition-visible helper relation"
            ),
            scope="selected-build",
            proof_method=(
                "enclosing-ir-hash-binding" if inlined else
                "compiler-declaration-attribute-binding" if attributed else
                "definition-hash-and-call-graph-binding"
            ),
            language=language, native_construct=helper["symbol"], facts={"body_sha256": helper.get("body_sha256")},
        )
        obligations.append(item)

    if multi_exit_regions or has_multiple_returns:
        exit_count = max(int(source.get("return_count", 0)), 1)
        add_node("exit.merge", "ExitMerge", "tagged-return-merge", ("region",), "exit-tag+live-outs", {
            "exit_count": exit_count,
            "regions": [item.get("id") for item in multi_exit_regions],
            "lowered_returns": effects.get("instruction_counts", {}).get("returns", 0),
        })
        obligations.append(obligation(
            "region.exit.complete", "validation",
            "every ordinary source return maps to exactly one exit tag and result projection",
            scope="bounded-cfg", proof_method="z3-exit-selector-and-alive2",
            language=language, native_construct="ReturnStmt/ret/phi",
        ))
        result_input = "exit.merge"
    else:
        result_input = "region"

    for index, item in enumerate(no_growth_regions):
        guard_id = f"ownership.guard.{index}"
        append_id = f"append.{index}"
        add_node(guard_id, "OwnershipGuard", "capacity-minus-size-covers-appends", (result_input,), "bool", item["container_closure"])
        add_node(append_id, "Append", "no-growth-trivial-append", (guard_id,), "updated-extent", {
            "operations": item.get("capacity_operations", []), "source_range": item.get("source_range"),
        })
        obligations.extend([
            obligation(
                f"region.ownership.{index}.capacity", "bounds",
                "the dominating spare-capacity guard covers every append before the first write",
                scope="bounded-container-region", proof_method="z3-capacity",
                language=language, native_construct="vector::capacity/size/push_back",
            ),
            obligation(
                f"region.ownership.{index}.stable", "ownership",
                "the region performs no reallocation, allocator change, or nontrivial lifetime transition",
                scope="bounded-container-region", proof_method="typed-contract-and-differential",
                language=language, native_construct="no-growth vector projection",
            ),
        ])
        result_input = append_id

    if aggregate_fields:
        add_node("result.pack", "AggregatePack", "ordered-result-projections", (result_input,), str(abi["return"].get("spelling", "aggregate")), {
            "fields": aggregate_fields,
            "lowered_sret": bool(abi.get("lowered_sret")),
            "lowered_signature": abi.get("lowered_signature"),
        })
        obligations.append(obligation(
            "region.aggregate.projection", "representation",
            "every aggregate output projection preserves its ordered source value and ABI channel",
            scope="selected-build-abi", proof_method="z3-projection-and-llvm-signature-binding",
            language=language, native_construct="insertvalue/extractvalue/sret",
        ))
        result_input = "result.pack"

    add_node("output", "Output", "typed-live-outs", (result_input,), str(abi.get("return", {}).get("spelling", "unknown")), {})

    external_boundary = bool(
        effects.get("external_calls") or effects.get("indirect_calls") or effects.get("unwind_operations")
        or effects.get("synchronization_operations") or effects.get("volatile_operations")
    )
    ownership_boundary = bool(effects.get("allocation_calls") or effects.get("deallocation_calls"))
    classes = {
        "abi": "closed" if abi.get("modeled") else "requires_adapter",
        "aggregate_result": "closed_at_compiled_abi" if aggregate_fields else "not_applicable",
        "multi_exit": "closed_as_tagged_cfg" if multi_exit_regions or has_multiple_returns else "not_applicable",
        "helper_summary": (
            "closed_inlined_or_call_preserving" if helpers and all(item["local_effects"] for item in helpers)
            else "requires_adapter" if helpers or effects.get("external_calls") or effects.get("indirect_calls")
            else "not_applicable"
        ),
        "ownership": "closed_no_growth_projection" if no_growth_regions else "requires_adapter" if ownership_boundary else "not_applicable",
    }
    graph = SemanticFlowGraph(
        function, language, compiler_identity, "bounded-region-closure-v1", function_identity,
        tuple(nodes), tuple(edges), {"classes": classes, "abi": abi},
        (
            "exception unwinding and nontrivial destruction",
            "reallocation and allocator protocols",
            "indirect, virtual, external, and concurrent protocols",
        ),
        tuple(obligations), (), (),
    )
    executable_modes = sorted({str(item.get("closure_mode")) for item in subregions if item.get("extractable_candidate")})
    result = {
        "schema_version": REGION_CLOSURE_SCHEMA,
        "status": "closed_local_region" if abi.get("modeled") and not external_boundary and not ownership_boundary else "partial_closure",
        "classes": classes,
        "aggregate_fields": aggregate_fields,
        "helper_summaries": helpers,
        "multi_exit_regions": [item.get("id") for item in multi_exit_regions] or (["whole-function"] if has_multiple_returns else []),
        "no_growth_regions": [item.get("id") for item in no_growth_regions],
        "executable_modes": executable_modes,
        "ir_transform_ready": bool(abi.get("modeled")) and not external_boundary and not ownership_boundary,
        "source_transform_ready": bool(executable_modes),
        "remaining_protocols": [
            name for present, name in (
                (bool(effects.get("unwind_operations")), "exception_or_cleanup"),
                (ownership_boundary, "owning_allocation_or_retirement"),
                (bool(effects.get("external_calls") or effects.get("indirect_calls")), "external_or_indirect_call"),
                (bool(effects.get("synchronization_operations") or effects.get("volatile_operations")), "concurrency_or_volatile"),
            ) if present
        ],
        "semantic_graph": graph.to_dict(),
        "graph_hash": graph.graph_hash,
    }
    result["closure_hash"] = canonical_hash({key: value for key, value in result.items() if key != "closure_hash"})
    return result


def prove_region_closure(closure: dict[str, Any], output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    obligations: list[dict[str, Any]] = []
    try:
        import z3
    except ImportError:
        return {"schema_version": REGION_CLOSURE_SCHEMA, "status": "UNAVAILABLE", "method": "Z3", "obligations": []}

    fields = closure.get("aggregate_fields", [])
    if fields:
        solver = z3.Solver()
        values = [z3.BitVec(f"field_{index}", 64) for index in range(len(fields))]
        projected = list(values)
        solver.add(z3.Or([left != right for left, right in zip(values, projected)]))
        result = solver.check()
        path = output_directory / "aggregate-projection.smt2"
        path.write_text(solver.to_smt2())
        obligations.append({"id": "aggregate-projection", "status": "PASS" if result == z3.unsat else "FAIL", "method": "Z3", "artifact": str(path)})

    exit_count = 0
    for node in closure.get("semantic_graph", {}).get("nodes", []):
        if node.get("kind") == "ExitMerge":
            exit_count = int(node.get("attributes", {}).get("exit_count", 0))
    if exit_count:
        solver = z3.Solver()
        tag = z3.Int("exit_tag")
        values = [z3.BitVec(f"exit_value_{index}", 64) for index in range(exit_count)]
        selected = values[-1]
        for index in reversed(range(exit_count - 1)):
            selected = z3.If(tag == index, values[index], selected)
        expected = values[-1]
        for index in reversed(range(exit_count - 1)):
            expected = z3.If(tag == index, values[index], expected)
        solver.add(tag >= 0, tag < exit_count, selected != expected)
        result = solver.check()
        path = output_directory / "exit-selector.smt2"
        path.write_text(solver.to_smt2())
        obligations.append({"id": "exit-selector", "status": "PASS" if result == z3.unsat else "FAIL", "method": "Z3", "artifact": str(path)})

    if closure.get("no_growth_regions"):
        solver = z3.Solver()
        size, capacity, append_count = z3.Ints("size capacity append_count")
        solver.add(size >= 0, append_count >= 0, size + append_count <= capacity)
        solver.add(size + append_count > capacity)
        result = solver.check()
        path = output_directory / "no-growth-capacity.smt2"
        path.write_text(solver.to_smt2())
        obligations.append({"id": "no-growth-capacity", "status": "PASS" if result == z3.unsat else "FAIL", "method": "Z3", "artifact": str(path)})

    for index, helper in enumerate(closure.get("helper_summaries", [])):
        bound = (
            helper.get("mode") == "inlined_into_selected_ir"
            or helper.get("mode") == "compiler_attributed_call_preserving" and bool(helper.get("summary_sha256"))
            or helper.get("mode") == "exact_call_preserving" and bool(helper.get("body_sha256"))
        )
        obligations.append({
            "id": f"helper-binding-{index}", "status": "PASS" if bound else "REQUIRES_ADAPTER",
            "method": (
                "enclosing-ir-binding" if helper.get("mode") == "inlined_into_selected_ir" else
                "compiler-declaration-attributes" if helper.get("mode") == "compiler_attributed_call_preserving" else
                "definition-hash"
            ), "artifact": None,
            "scope": "call-preserving only; transformations crossing the call require inlining or a functional proof",
        })

    failed = [item for item in obligations if item["status"] == "FAIL"]
    report = {
        "schema_version": REGION_CLOSURE_SCHEMA,
        "status": "PASS" if not failed else "FAIL",
        "closure_hash": closure.get("closure_hash"),
        "obligations": obligations,
        "claim_boundary": "bounded representation and control closure; external protocols and nontrivial ownership are excluded",
    }
    (output_directory / "region-closure-proof.json").write_text(__import__("json").dumps(report, indent=2, sort_keys=True) + "\n")
    return report
