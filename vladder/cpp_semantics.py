from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable


CPP_SEMANTIC_SCHEMA = "vladder-cpp-semantics-v3"


@dataclass(frozen=True)
class CppTypeDescriptor:
    spelling: str
    role: str
    category: str
    element_type: str | None
    const: bool
    borrowed: bool
    ownership: str
    proof_model: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def walk_ast(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield node
    for child in node.get("inner", []):
        if isinstance(child, dict):
            yield from walk_ast(child)


def normalize_type(spelling: str) -> str:
    return re.sub(r"\s+", " ", spelling).strip()


def function_return_type(function_type: str) -> str:
    match = re.match(r"^(.*?)\s+\(", normalize_type(function_type))
    return match.group(1).strip() if match else "unknown"


def _template_argument(spelling: str, template: str) -> str | None:
    compact = normalize_type(spelling)
    start = compact.find(template + "<")
    if start < 0:
        return None
    start += len(template) + 1
    depth = 1
    for index in range(start, len(compact)):
        if compact[index] == "<":
            depth += 1
        elif compact[index] == ">":
            depth -= 1
            if depth == 0:
                value = compact[start:index]
                return value.split(",", 1)[0].strip()
    return None


def describe_cpp_type(spelling: str, role: str) -> CppTypeDescriptor:
    normalized = normalize_type(spelling)
    base = normalized.replace("const ", "").replace(" const", "").strip()
    scalar_patterns = (
        r"(?:signed |unsigned )?(?:char|short|int|long|long long)",
        r"(?:std::)?(?:u?int(?:8|16|32|64)_t|size_t|ptrdiff_t)",
        r"(?:bool|float|double|long double|std::byte)",
    )
    is_const = "const" in normalized
    span_element = _template_argument(normalized, "std::span") or _template_argument(normalized, "span")
    vector_element = _template_argument(normalized, "std::vector") or _template_argument(normalized, "vector")
    if span_element is not None:
        return CppTypeDescriptor(normalized, role, "span", normalize_type(span_element), "const" in span_element, True, "borrowed", "pointer_extent")
    if vector_element is not None:
        borrowed = "&" in normalized
        return CppTypeDescriptor(
            normalized, role, "borrowed_vector" if borrowed else "owning_vector", normalize_type(vector_element),
            "const" in normalized, borrowed, "borrowed" if borrowed else "owning", "pointer_size_capacity" if borrowed else "allocator_protocol",
        )
    if re.search(r"\(\s*\*.*\)", normalized) or "std::function<" in normalized:
        return CppTypeDescriptor(normalized, role, "callable", None, is_const, True, "external", "callable_contract")
    if normalized.endswith("*") or "* const" in normalized:
        element = re.sub(r"\s*\*\s*(?:const)?$", "", normalized).strip()
        return CppTypeDescriptor(normalized, role, "pointer", element, is_const, True, "borrowed", "pointer_extent")
    if any(re.fullmatch(pattern, base) for pattern in scalar_patterns):
        return CppTypeDescriptor(normalized, role, "scalar", base, is_const, True, "value", "bitvector_or_ieee")
    if normalized == "void":
        return CppTypeDescriptor(normalized, role, "void", None, False, True, "none", "none")
    if normalized.endswith("&"):
        return CppTypeDescriptor(normalized, role, "aggregate_reference", normalized.rstrip("& "), is_const, True, "borrowed", "state_projection")
    return CppTypeDescriptor(normalized, role, "aggregate_value", normalized, is_const, False, "value", "lowered_aggregate")


def describe_abi(function_type: str, parameters: list[dict[str, str]], lowered_signature: str) -> dict[str, Any]:
    result = describe_cpp_type(function_return_type(function_type), "return")
    arguments = [describe_cpp_type(item["type"], "parameter") for item in parameters]
    lowered_sret = bool(re.search(r"\bsret(?:\(|\b)", lowered_signature))
    lowered_return = re.match(r"^define\s+(?:[-A-Za-z0-9_]+\s+)*([^@]+?)\s+@", lowered_signature)
    lowered_return_type = normalize_type(lowered_return.group(1)) if lowered_return else "unknown"
    lowered_register_result = result.category == "aggregate_value" and lowered_return_type != "void" and not lowered_sret
    accepted_categories = {"scalar", "pointer", "span", "borrowed_vector", "aggregate_reference"}
    parameters_modeled = all(item.category in accepted_categories for item in arguments)
    result_modeled = result.category in {"void", "scalar"} or (
        result.category == "aggregate_value" and (lowered_sret or lowered_register_result)
    )
    return {
        "schema_version": CPP_SEMANTIC_SCHEMA,
        "return": result.to_dict(),
        "parameters": [item.to_dict() for item in arguments],
        "lowered_signature": lowered_signature,
        "lowered_sret": lowered_sret,
        "lowered_return_type": lowered_return_type,
        "lowered_register_aggregate": lowered_register_result,
        "parameters_modeled": parameters_modeled,
        "result_modeled": result_modeled,
        "modeled": parameters_modeled and result_modeled,
    }


def _extract_function(text: str, symbol: str) -> tuple[str, str]:
    escaped = re.escape(symbol)
    match = re.search(rf'^define\s+.*@(?:"{escaped}"|{escaped})\([^\n]*\).*\{{\s*$', text, re.MULTILINE)
    if not match:
        raise ValueError(f"selected symbol {symbol!r} is absent from effect IR")
    start = match.start()
    opening = text.find("{", match.start(), match.end())
    depth = 0
    end = None
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError("unterminated LLVM function")
    return text[start:end], text[match.start(): text.find("\n", match.start())]


def _attribute_group(text: str, signature: str) -> str:
    matches = re.findall(r"#(\d+)", signature)
    match = matches[-1] if matches else None
    if not match:
        return ""
    group = re.search(rf"^attributes\s+#{match}\s*=\s*\{{(.*?)\}}\s*$", text, re.MULTILINE)
    return group.group(1) if group else ""


def _call_targets(body: str, opcode: str) -> tuple[list[str], int]:
    targets: list[str] = []
    indirect = 0
    for line in body.splitlines():
        if not re.search(rf"\b{opcode}\b", line):
            continue
        match = re.search(r'@(?:"([^"]+)"|([-A-Za-z$._0-9]+))\s*\(', line)
        if match:
            targets.append(match.group(1) or match.group(2))
        elif re.search(rf"\b{opcode}\b.*%[-A-Za-z$._0-9]+\s*\(", line):
            indirect += 1
    return targets, indirect


def analyze_ir_effects(module_text: str, symbol: str, _seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    if symbol in _seen:
        raise ValueError(f"recursive effect closure at {symbol}")
    seen = _seen | {symbol}
    body, signature = _extract_function(module_text, symbol)
    attrs = _attribute_group(module_text, signature)
    joined_attrs = signature + " " + attrs
    calls, indirect_calls = _call_targets(body, "call")
    invokes, indirect_invokes = _call_targets(body, "invoke")
    all_targets = calls + invokes
    intrinsics = sorted({target for target in all_targets if target.startswith("llvm.")})
    remaining = sorted({target for target in all_targets if not target.startswith("llvm.")})
    allocation_re = re.compile(r"(?:^|\.)(?:malloc|calloc|realloc|aligned_alloc)$|(?:^|_)(?:Zn[aw]|allocate|make_unique|make_shared)")
    deallocation_re = re.compile(r"(?:^|\.)(?:free)$|(?:^|_)(?:Zd[al]|deallocate)")
    allocation_calls = sorted(target for target in remaining if allocation_re.search(target))
    deallocation_calls = sorted(target for target in remaining if deallocation_re.search(target))
    synchronization = bool(re.search(r"\b(?:atomicrmw|cmpxchg|fence)\b|\bload\s+atomic\b|\bstore\s+atomic\b", body))
    volatile = bool(re.search(r"\b(?:load|store)\s+volatile\b", body))
    unwind = bool(invokes or re.search(r"\b(?:landingpad|catchswitch|catchpad|cleanuppad|resume)\b", body))
    nounwind = bool(re.search(r"\bnounwind\b", joined_attrs))
    nofree = bool(re.search(r"\bnofree\b", joined_attrs))
    nosync = bool(re.search(r"\bnosync\b", joined_attrs))
    memory_match = re.search(r"\bmemory\(([^)]*)\)", joined_attrs)
    unresolved = set(remaining) - set(allocation_calls) - set(deallocation_calls)
    internal_calls: dict[str, dict[str, Any]] = {}
    nested_external: set[str] = set()
    nested_allocations: set[str] = set()
    nested_deallocations: set[str] = set()
    nested_unwind = False
    nested_sync = False
    for target in sorted(unresolved):
        try:
            nested = analyze_ir_effects(module_text, target, seen)
        except ValueError:
            nested_external.add(target)
            continue
        internal_calls[target] = {
            "local_effects": nested["local_effects"],
            "nounwind": nested["nounwind"],
            "memory_effect": nested["memory_effect"],
        }
        if not nested["local_effects"]:
            # A definition-visible helper is not automatically harmless. Preserve a
            # conservative boundary marker when its transitive effects exceed the
            # local proof envelope, even if its own callees were all resolved.
            nested_external.add(target)
        nested_external.update(nested["external_calls"])
        nested_allocations.update(nested["allocation_calls"])
        nested_deallocations.update(nested["deallocation_calls"])
        nested_unwind = nested_unwind or nested["unwind_operations"] or not nested["nounwind"]
        nested_sync = nested_sync or nested["synchronization_operations"]
    allocation_calls = sorted(set(allocation_calls) | nested_allocations)
    deallocation_calls = sorted(set(deallocation_calls) | nested_deallocations)
    external_calls = sorted(nested_external)
    global_stores = len(re.findall(r"\bstore\b[^\n]*,\s+ptr\s+@[-A-Za-z$._0-9]+", body))
    unwind = unwind or nested_unwind
    synchronization = synchronization or nested_sync
    local = (
        nounwind and not unwind and not allocation_calls and not deallocation_calls and not synchronization
        and not volatile and not external_calls and indirect_calls + indirect_invokes == 0 and global_stores == 0
    )
    return {
        "schema_version": CPP_SEMANTIC_SCHEMA,
        "signature": signature,
        "attributes": attrs.strip(),
        "nounwind": nounwind,
        "nofree": nofree,
        "nosync": nosync,
        "memory_effect": memory_match.group(1) if memory_match else "unknown",
        "calls": sorted(set(calls)),
        "invokes": sorted(set(invokes)),
        "intrinsics": intrinsics,
        "remaining_direct_calls": remaining,
        "internal_call_summaries": internal_calls,
        "external_calls": external_calls,
        "allocation_calls": allocation_calls,
        "deallocation_calls": deallocation_calls,
        "indirect_calls": indirect_calls + indirect_invokes,
        "unwind_operations": unwind,
        "synchronization_operations": synchronization,
        "volatile_operations": volatile,
        "global_stores": global_stores,
        "instruction_counts": {
            "loads": len(re.findall(r"\bload\b", body)),
            "stores": len(re.findall(r"\bstore\b", body)),
            "branches": len(re.findall(r"\bbr\b", body)),
            "phis": len(re.findall(r"\bphi\b", body)),
            "calls": len(calls),
            "invokes": len(invokes),
        },
        "local_effects": local,
    }


def source_semantics(node: dict[str, Any], function_source: str) -> dict[str, Any]:
    nodes = list(walk_ast(node))
    kinds = {str(item.get("kind")) for item in nodes}
    calls: list[str] = []
    constructors: list[str] = []
    for item in nodes:
        if item.get("kind") in {"CXXConstructExpr", "CXXTemporaryObjectExpr"}:
            constructors.append(normalize_type(str(item.get("type", {}).get("qualType", "unknown"))))
        if item.get("kind") in {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr"}:
            names: list[str] = []
            for child in walk_ast(item):
                if child.get("kind") == "MemberExpr" and child.get("name"):
                    names.append(str(child["name"]))
                referenced = child.get("referencedDecl")
                if isinstance(referenced, dict) and referenced.get("name"):
                    names.append(str(referenced["name"]))
            calls.append(names[0] if names else "<indirect>")
    explicit_throw = bool(kinds & {"CXXThrowExpr", "CXXTryStmt", "CXXCatchStmt"})
    explicit_allocation = bool(kinds & {"CXXNewExpr", "CXXDeleteExpr"}) or bool(
        re.search(r"\b(?:new|delete|make_unique|make_shared|unique_ptr|shared_ptr)\b", function_source)
    )
    memory_order = bool(re.search(r"\b(?:atomic\w*|memory_order\w*|mutex|lock_guard|unique_lock|condition_variable|volatile)\b", function_source))
    runtime_control = bool(kinds & {"GCCAsmStmt", "MSAsmStmt", "CoroutineBodyStmt", "CoawaitExpr", "CoyieldExpr"})
    return {
        "calls": sorted(set(calls)),
        "constructors": dict(sorted(Counter(constructors).items())),
        "explicit_throw": explicit_throw,
        "explicit_allocation": explicit_allocation,
        "object_state": "CXXThisExpr" in kinds,
        "memory_order_syntax": memory_order,
        "runtime_control": runtime_control,
        "loop_count": sum(kind in {"ForStmt", "CXXForRangeStmt", "WhileStmt", "DoStmt"} for kind in (item.get("kind") for item in nodes)),
    }


def helper_closure(source_calls: list[str], effects: dict[str, Any]) -> dict[str, Any]:
    remaining = effects["remaining_direct_calls"]
    internal = effects.get("internal_call_summaries", {})
    if not effects["external_calls"] and not effects["indirect_calls"] and all(
        summary.get("local_effects") for summary in internal.values()
    ):
        label = "definition_visible_local_summary" if remaining else "inlined_or_folded"
        disposition = {name: label for name in source_calls}
    elif not remaining and not effects["indirect_calls"]:
        disposition = {name: "inlined_or_folded" for name in source_calls}
    else:
        disposition = {name: "requires_mapping_or_summary" for name in source_calls}
    return {"source_calls": source_calls, "remaining_ir_calls": remaining, "disposition": disposition}


def discover_subregions(node: dict[str, Any], source_text: str) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    loop_kinds = {"ForStmt", "CXXForRangeStmt", "WhileStmt", "DoStmt"}
    modeled_calls = {"operator[]", "size", "data", "begin", "end", "operator*", "operator++", "operator==", "operator!=", "front", "empty"}
    capacity_calls = {"push_back", "emplace_back", "insert", "reserve", "resize"}
    function_range = node.get("range", {})
    function_begin = function_range.get("begin", {}).get("offset")
    function_end = function_range.get("end", {}).get("offset")
    for index, item in enumerate(candidate for candidate in walk_ast(node) if candidate.get("kind") in loop_kinds):
        source_range = item.get("range", {})
        begin_location = source_range.get("begin", {})
        end_location = source_range.get("end", {})
        begin = begin_location.get("offset")
        end = end_location.get("offset")
        token_length = end_location.get("tokLen", 1)
        if not isinstance(begin, int) or not isinstance(end, int):
            continue
        end += int(token_length)
        macro_origin = "expansionLoc" in begin_location or "spellingLoc" in begin_location or "expansionLoc" in end_location or "spellingLoc" in end_location
        outside_function = (
            isinstance(function_begin, int) and begin < function_begin
            or isinstance(function_end, int) and end > function_end + int(function_range.get("end", {}).get("tokLen", 1))
            or begin < 0 or end > len(source_text) or begin >= end
        )
        snippet = source_text[begin:end]
        semantics = source_semantics(item, snippet)
        hard_hazards = []
        if semantics["explicit_throw"]:
            hard_hazards.append("exception")
        if semantics["explicit_allocation"]:
            hard_hazards.append("allocation")
        if semantics["memory_order_syntax"]:
            hard_hazards.append("memory_order")
        if semantics["runtime_control"]:
            hard_hazards.append("runtime_control")
        if semantics["object_state"]:
            hard_hazards.append("object_state")
        escaping_control = sorted({
            str(child.get("kind")) for child in walk_ast(item)
            if child.get("kind") in {"ReturnStmt", "GotoStmt", "IndirectGotoStmt", "CoreturnStmt"}
        })
        calls = set(semantics["calls"])
        unmodeled = sorted(calls - modeled_calls - capacity_calls)
        capacity = sorted(calls & capacity_calls)
        if unmodeled:
            hard_hazards.append("external_call")
        if capacity:
            hard_hazards.append("capacity_mutation")
        if macro_origin or outside_function:
            hard_hazards.append("source_range")
        declarations = {
            str(child.get("name")) for child in walk_ast(item)
            if child.get("kind") in {"VarDecl", "ParmVarDecl"} and child.get("name")
        }
        references = {
            str(child.get("referencedDecl", {}).get("name")) for child in walk_ast(item)
            if isinstance(child.get("referencedDecl"), dict) and child["referencedDecl"].get("name")
        }
        regions.append({
            "id": f"region-{index:03d}",
            "kind": str(item.get("kind")),
            "source_range": [begin, end],
            "source_sha256": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
            "macro_origin": macro_origin,
            "outside_selected_function": outside_function,
            "calls": sorted(calls),
            "unmodeled_source_calls": unmodeled,
            "capacity_operations": capacity,
            "hard_hazards": hard_hazards,
            "escaping_control": escaping_control,
            "boundary": {
                "declared_locals": sorted(declarations),
                "referenced_identifiers": sorted(references),
                "candidate_live_ins": sorted(references - declarations),
            },
            "classification": (
                "blocked" if hard_hazards else
                "bounded_container_candidate" if capacity else
                "helper_closure_candidate" if unmodeled else
                "extractable_local_candidate"
            ),
            "extractable_candidate": not hard_hazards and not escaping_control,
        })
    return regions


def classify_support_tier(
    *, canonical_transform: bool, abi: dict[str, Any], source: dict[str, Any], effects: dict[str, Any], subregions: list[dict[str, Any]]
) -> dict[str, Any]:
    source_local = not (
        source["explicit_throw"] or source["explicit_allocation"] or source["memory_order_syntax"] or source["runtime_control"]
    )
    if canonical_transform:
        return {"tier": "canonical_source_transform", "accepted": True, "transformation_ready": True}
    if effects["local_effects"] and abi["modeled"] and source_local and not source["object_state"]:
        return {"tier": "whole_function_local_ir", "accepted": True, "transformation_ready": False}
    if effects["local_effects"] and abi["modeled"] and source_local and source["object_state"]:
        return {"tier": "bounded_state_transition", "accepted": True, "transformation_ready": False}
    if any(
        item["extractable_candidate"] and item["classification"] != "helper_closure_candidate"
        for item in subregions
    ):
        return {"tier": "extractable_subregions", "accepted": True, "transformation_ready": False}
    return {"tier": "external_protocol", "accepted": False, "transformation_ready": False}


def build_cpp_information_flow(
    abi: dict[str, Any], source: dict[str, Any], effects: dict[str, Any], subregions: list[dict[str, Any]]
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for index, parameter in enumerate(abi["parameters"]):
        node_id = f"parameter-{index}"
        nodes.append({"id": node_id, "kind": "InputBoundary", "type": parameter})
        edges.append({"source": node_id, "destination": "compiled-region", "kind": "data_or_state"})
    nodes.append({
        "id": "compiled-region", "kind": "CompiledInformationFlow",
        "attributes": {
            "memory_effect": effects["memory_effect"],
            "instruction_counts": effects["instruction_counts"],
            "local_effects": effects["local_effects"],
        },
    })
    nodes.append({"id": "result", "kind": "OutputBoundary", "type": abi["return"]})
    edges.append({"source": "compiled-region", "destination": "result", "kind": "result"})
    for index, call in enumerate(source["calls"]):
        node_id = f"source-call-{index}"
        disposition = "external_or_summarized" if effects["external_calls"] else "lowered_into_compiled_region"
        nodes.append({"id": node_id, "kind": "SourceCall", "name": call, "disposition": disposition})
        edges.append({"source": node_id, "destination": "compiled-region", "kind": "lowering_provenance"})
    for region in subregions:
        node_id = region["id"]
        nodes.append({
            "id": node_id, "kind": "SourceSubregion", "source_range": region["source_range"],
            "classification": region["classification"], "boundary": region["boundary"],
        })
        edges.append({"source": node_id, "destination": "compiled-region", "kind": "source_provenance"})
    graph = {
        "schema_version": "vladder-cpp-information-flow-v1",
        "nodes": nodes,
        "edges": edges,
        "invariants": {
            "compiler_build_specific": True,
            "source_object_state": source["object_state"],
            "remaining_external_calls": effects["external_calls"],
            "unwind": effects["unwind_operations"],
            "synchronization": effects["synchronization_operations"],
        },
    }
    canonical = json.dumps(graph, sort_keys=True, separators=(",", ":"))
    graph["graph_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return graph
