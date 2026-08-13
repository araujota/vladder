from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .cpp_protocols import (
    classify_cpp_call,
    exceptional_cfg_summary,
    memory_order_summary,
    object_state_projection,
)
from .language_adapter import (
    ProtocolTransition,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    obligation,
)


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


def _source_aggregate_fields(
    result: CppTypeDescriptor,
    documents: list[dict[str, Any]] | None,
    source_text: str | None,
) -> list[dict[str, str]]:
    if result.category != "aggregate_value":
        return []
    wanted = normalize_type(str(result.element_type or result.spelling)).split("::")[-1]
    for document in documents or []:
        for item in walk_ast(document):
            if item.get("kind") not in {"CXXRecordDecl", "RecordDecl"} or item.get("name") != wanted:
                continue
            fields = [
                {"name": str(child.get("name", f"field_{index}")), "type": normalize_type(str(child.get("type", {}).get("qualType", "unknown"))), "provenance": "clang-ast"}
                for index, child in enumerate(item.get("inner", [])) if child.get("kind") == "FieldDecl"
            ]
            if fields:
                return fields
    # The function-filtered JSON AST may omit the record declaration. Preserve a
    # conservative fallback for ordinary, non-macro POD declarations; the exact
    # compiler-lowered ABI remains the authoritative physical binding.
    if source_text:
        record = re.search(rf"\b(?:struct|class)\s+{re.escape(wanted)}\s*\{{(.*?)\}}\s*;", source_text, re.DOTALL)
        if record:
            fields = []
            for statement in record.group(1).split(";"):
                declaration = re.sub(r"//.*", "", statement).strip()
                match = re.match(r"(.+?)\s+([A-Za-z_]\w*)\s*$", declaration)
                if match and "(" not in declaration:
                    fields.append({"name": match.group(2), "type": normalize_type(match.group(1)), "provenance": "source-pod-fallback"})
            if fields:
                return fields
    return []


def describe_abi(
    function_type: str,
    parameters: list[dict[str, str]],
    lowered_signature: str,
    documents: list[dict[str, Any]] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    result = describe_cpp_type(function_return_type(function_type), "return")
    arguments = []
    for item in parameters:
        descriptor = describe_cpp_type(item.get("canonical_type") or item["type"], "parameter").to_dict()
        descriptor["source_spelling"] = item["type"]
        arguments.append(descriptor)
    lowered_sret = bool(re.search(r"\bsret(?:\(|\b)", lowered_signature))
    lowered_return = re.match(r"^define\s+(?:[-A-Za-z0-9_]+\s+)*([^@]+?)\s+@", lowered_signature)
    lowered_return_type = normalize_type(lowered_return.group(1)) if lowered_return else "unknown"
    lowered_register_result = result.category == "aggregate_value" and lowered_return_type != "void" and not lowered_sret
    source_fields = _source_aggregate_fields(result, documents, source_text)
    accepted_categories = {"scalar", "pointer", "span", "borrowed_vector", "aggregate_reference"}
    parameters_modeled = all(item["category"] in accepted_categories for item in arguments)
    result_modeled = result.category in {"void", "scalar"} or (
        result.category == "aggregate_value" and (lowered_sret or lowered_register_result)
    )
    return {
        "schema_version": CPP_SEMANTIC_SCHEMA,
        "return": result.to_dict(),
        "parameters": arguments,
        "lowered_signature": lowered_signature,
        "lowered_sret": lowered_sret,
        "lowered_return_type": lowered_return_type,
        "lowered_register_aggregate": lowered_register_result,
        "source_aggregate_fields": source_fields,
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


def _declaration_summary(module_text: str, symbol: str) -> dict[str, Any] | None:
    escaped = re.escape(symbol)
    declaration = re.search(
        rf'^declare\s+.*@(?:"{escaped}"|{escaped})\([^\n]*\).*$',
        module_text,
        re.MULTILINE,
    )
    if not declaration:
        return None
    signature = declaration.group(0)
    attrs = _attribute_group(module_text, signature)
    joined = signature + " " + attrs
    memory = re.search(r"\bmemory\(([^)]*)\)", joined)
    standard_nocallback = bool(re.search(
        r"^(?:memcpy|memmove|memset|memcmp|bcmp|memchr|strlen|strnlen|"
        r"__memcpy_chk|__memmove_chk|__memset_chk)$",
        symbol,
    ))
    facts = {
        "nounwind": bool(re.search(r"\bnounwind\b", joined)),
        "nofree": bool(re.search(r"\bnofree\b", joined)),
        "nosync": bool(re.search(r"\bnosync\b", joined)),
        "nocallback": bool(re.search(r"\bnocallback\b", joined)) or standard_nocallback,
        "willreturn": bool(re.search(r"\bwillreturn\b", joined)) or standard_nocallback,
        "memory_effect": memory.group(1) if memory else "unknown",
        "signature": signature,
        "attributes": attrs,
    }
    facts["closed_call_preserving_effects"] = bool(
        facts["nounwind"] and facts["nofree"] and facts["nosync"]
        and facts["nocallback"] and facts["willreturn"] and memory
    )
    facts["summary_sha256"] = hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return facts


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
    declared_calls: dict[str, dict[str, Any]] = {}
    protocol_calls: dict[str, dict[str, Any]] = {}
    recursive_calls: list[str] = []
    nested_external: set[str] = set()
    nested_allocations: set[str] = set()
    nested_deallocations: set[str] = set()
    nested_unwind = False
    nested_sync = False
    nested_volatile = False
    nested_global_stores = 0
    for target in sorted(unresolved):
        if target in seen:
            recursive_calls.append(target)
            recursive_body, recursive_signature = _extract_function(module_text, target)
            recursive_attrs = _attribute_group(module_text, recursive_signature)
            recursive_memory = re.search(
                r"\bmemory\(([^)]*)\)", recursive_signature + " " + recursive_attrs
            )
            internal_calls[target] = {
                "local_effects": True,
                "recursive_edge": True,
                "nounwind": bool(re.search(r"\bnounwind\b", recursive_signature + " " + recursive_attrs)),
                "memory_effect": recursive_memory.group(1) if recursive_memory else "unknown",
                "function_body_sha256": hashlib.sha256(recursive_body.encode()).hexdigest(),
                "instruction_counts": {},
            }
            continue
        try:
            nested = analyze_ir_effects(module_text, target, seen)
        except ValueError:
            declared = _declaration_summary(module_text, target)
            if declared and declared["closed_call_preserving_effects"]:
                declared_calls[target] = declared
            else:
                protocol = classify_cpp_call(target)
                if protocol is not None:
                    protocol_calls[target] = protocol.to_dict()
                    nested_allocations.update(
                        [target] if "allocate" in protocol.flags else []
                    )
                    nested_deallocations.update(
                        [target] if "deallocate" in protocol.flags else []
                    )
                    nested_unwind = nested_unwind or "unwind" in protocol.flags
                    nested_sync = nested_sync or "synchronize" in protocol.flags
                else:
                    nested_external.add(target)
            continue
        internal_calls[target] = {
            "local_effects": nested["local_effects"],
            "nounwind": nested["nounwind"],
            "memory_effect": nested["memory_effect"],
            "function_body_sha256": nested["function_body_sha256"],
            "instruction_counts": nested["instruction_counts"],
            "external_calls": nested["external_calls"],
            "allocation_calls": nested["allocation_calls"],
            "deallocation_calls": nested["deallocation_calls"],
            "unwind_operations": nested["unwind_operations"],
            "synchronization_operations": nested["synchronization_operations"],
            "volatile_operations": nested["volatile_operations"],
            "global_stores": nested["global_stores"],
        }
        nested_external.update(nested["external_calls"])
        nested_allocations.update(nested["allocation_calls"])
        nested_deallocations.update(nested["deallocation_calls"])
        nested_unwind = nested_unwind or nested["unwind_operations"] or not nested["nounwind"]
        nested_sync = nested_sync or nested["synchronization_operations"]
        nested_volatile = nested_volatile or nested["volatile_operations"]
        nested_global_stores += int(nested["global_stores"])
    allocation_calls = sorted(set(allocation_calls) | nested_allocations)
    deallocation_calls = sorted(set(deallocation_calls) | nested_deallocations)
    external_calls = sorted(nested_external)
    global_stores = len(re.findall(r"\bstore\b[^\n]*,\s+ptr\s+@[-A-Za-z$._0-9]+", body)) + nested_global_stores
    unwind = unwind or nested_unwind
    synchronization = synchronization or nested_sync
    volatile = volatile or nested_volatile
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
        "declared_call_summaries": declared_calls,
        "protocol_call_summaries": protocol_calls,
        "recursive_calls": sorted(recursive_calls),
        "external_calls": external_calls,
        "allocation_calls": allocation_calls,
        "deallocation_calls": deallocation_calls,
        "indirect_calls": indirect_calls + indirect_invokes,
        "unwind_operations": unwind,
        "synchronization_operations": synchronization,
        "volatile_operations": volatile,
        "global_stores": global_stores,
        "function_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "exceptional_cfg": exceptional_cfg_summary(body),
        "memory_order": memory_order_summary(body),
        "object_state_projection": object_state_projection(body, signature),
        "aggregate_operations": {
            "extractvalue": len(re.findall(r"\bextractvalue\b", body)),
            "insertvalue": len(re.findall(r"\binsertvalue\b", body)),
            "sret_stores": len(re.findall(r"\bstore\b[^\n]*\bsret\b", body)),
        },
        "instruction_counts": {
            "loads": len(re.findall(r"\bload\b", body)),
            "stores": len(re.findall(r"\bstore\b", body)),
            "branches": len(re.findall(r"\bbr\b", body)),
            "phis": len(re.findall(r"\bphi\b", body)),
            "calls": len(calls),
            "invokes": len(invokes),
            "returns": len(re.findall(r"^\s*ret\b", body, re.MULTILINE)),
            "basic_blocks": len(re.findall(r"^[A-Za-z$._][-A-Za-z$._0-9]*:\s*(?:;.*)?$", body, re.MULTILINE)),
            "selects": len(re.findall(r"\bselect\b", body)),
        },
        "local_effects": local,
    }


def source_semantics(node: dict[str, Any], function_source: str) -> dict[str, Any]:
    nodes = list(walk_ast(node))
    kinds = {str(item.get("kind")) for item in nodes}
    calls: list[str] = []
    constructors: list[str] = []
    member_fields: list[dict[str, str]] = []
    for item in nodes:
        if item.get("kind") in {"CXXConstructExpr", "CXXTemporaryObjectExpr"}:
            constructors.append(normalize_type(str(item.get("type", {}).get("qualType", "unknown"))))
        if item.get("kind") == "MemberExpr":
            value_type = normalize_type(str(item.get("type", {}).get("qualType", "unknown")))
            if value_type != "<bound member function type>" and item.get("name"):
                member_fields.append({"name": str(item["name"]), "type": value_type})
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
        "member_fields": [
            {"name": name, "type": value_type}
            for name, value_type in sorted({(item["name"], item["type"]) for item in member_fields})
        ],
        "memory_order_syntax": memory_order,
        "runtime_control": runtime_control,
        "return_count": sum(kind == "ReturnStmt" for kind in (item.get("kind") for item in nodes)),
        "break_count": sum(kind == "BreakStmt" for kind in (item.get("kind") for item in nodes)),
        "cleanup_syntax": bool(kinds & {"CXXBindTemporaryExpr", "CXXDeleteExpr", "CXXTryStmt"}),
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


def discover_subregions(
    node: dict[str, Any], source_text: str, effects: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    loop_kinds = {"ForStmt", "CXXForRangeStmt", "WhileStmt", "DoStmt"}
    modeled_calls = {"operator[]", "size", "data", "begin", "end", "operator*", "operator++", "operator==", "operator!=", "front", "empty"}
    capacity_calls = {"push_back", "emplace_back", "insert", "reserve", "resize"}
    function_range = node.get("range", {})
    function_begin = function_range.get("begin", {}).get("offset")
    function_end = function_range.get("end", {}).get("offset")
    function_token_length = int(function_range.get("end", {}).get("tokLen", 1))
    function_source = ""
    if isinstance(function_begin, int) and isinstance(function_end, int):
        function_source = source_text[function_begin : function_end + function_token_length]
    noexcept_boundary = "noexcept" in function_source
    vector_elements = {
        name: normalize_type(element)
        for element, name in re.findall(
            r"(?:std::)?vector\s*<\s*([^,>]+)(?:,[^>]*)?>\s*&?\s*([A-Za-z_]\w*)",
            function_source,
        )
    }
    trivial_element = re.compile(
        r"^(?:std::)?(?:u?int(?:8|16|32|64)_t|byte|char|short|int|long|float|double)$"
    )
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
        # Clang's statement range ends at the final expression token for an
        # unbraced loop body, excluding its syntactic semicolon. The capsule
        # must preserve that token to remain valid C++.
        if item.get("kind") in loop_kinds:
            cursor = end
            while cursor < len(source_text) and source_text[cursor].isspace():
                cursor += 1
            if cursor < len(source_text) and source_text[cursor] == ";":
                end = cursor + 1
        macro_origin = "expansionLoc" in begin_location or "spellingLoc" in begin_location or "expansionLoc" in end_location or "spellingLoc" in end_location
        outside_function = (
            isinstance(function_begin, int) and begin < function_begin
            or isinstance(function_end, int) and end > function_end + int(function_range.get("end", {}).get("tokLen", 1))
            or begin < 0 or end > len(source_text) or begin >= end
        )
        snippet = source_text[begin:end]
        append_receivers = set(re.findall(r"\b([A-Za-z_]\w*)\s*\.\s*(?:push_back|emplace_back)\s*\(", snippet))
        trivial_container = bool(append_receivers) and all(
            receiver in vector_elements and trivial_element.fullmatch(vector_elements[receiver])
            for receiver in append_receivers
        )
        prefix = source_text[function_begin:begin] if isinstance(function_begin, int) else ""
        capacity_guard_present = bool(
            re.search(
                r"\bif\s*\([^{};]*?\.capacity\s*\(\)[^{};]*?\.size\s*\(\)[^{};]*?\)\s*\{?\s*return\b",
                prefix,
                re.DOTALL,
            )
        )
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
        helper_summary_closed = bool(
            unmodeled and effects
            and not effects.get("external_calls") and not effects.get("indirect_calls")
            and (
                not effects.get("remaining_direct_calls")
                or bool(effects.get("internal_call_summaries"))
            )
        )
        capacity = sorted(calls & capacity_calls)
        if unmodeled and not helper_summary_closed:
            hard_hazards.append("external_call")
        bounded_no_growth = bool(
            capacity
            and set(capacity) <= {"push_back", "emplace_back"}
            and capacity_guard_present
            and noexcept_boundary
            and trivial_container
        )
        if capacity and not bounded_no_growth:
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
        # Clang's unroll/vector/interleave pragmas used by the selected-build
        # grammar are non-assumptive schedule hints: unlike ivdep or
        # vectorize(assume_safety), they do not waive dependency, exception,
        # atomic, alias, or call-order legality.  Therefore an owning/effectful
        # loop may still be a source-preserving schedule candidate even when it
        # is not a lambda-isolatable functional proof unit.
        schedule_hint_eligible = not (
            macro_origin
            or outside_function
            or semantics["runtime_control"]
            or any(kind in {"GotoStmt", "IndirectGotoStmt", "CoreturnStmt"} for kind in escaping_control)
        )
        structured_return_exit = (
            bool(escaping_control)
            and set(escaping_control) == {"ReturnStmt"}
            and schedule_hint_eligible
        )
        closure_mode = (
            "whole_function_cfg" if structured_return_exit else
            "no_growth_container" if bounded_no_growth else
            "lambda_capsule" if not hard_hazards else
            "effect_preserving_schedule"
        )
        regions.append({
            "id": f"region-{index:03d}",
            "kind": str(item.get("kind")),
            "source_range": [begin, end],
            "source_sha256": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
            "macro_origin": macro_origin,
            "outside_selected_function": outside_function,
            "calls": sorted(calls),
            "unmodeled_source_calls": unmodeled,
            "helper_summary_closure": {
                "closed": helper_summary_closed,
                "mode": "inlined_or_exact_call_preserving" if helper_summary_closed else "not_applicable" if not unmodeled else "requires_adapter",
            },
            "capacity_operations": capacity,
            "container_closure": {
                "mode": "borrowed_no_growth" if bounded_no_growth else "unclosed" if capacity else "not_applicable",
                "capacity_guard": capacity_guard_present,
                "guard_dominates_region": capacity_guard_present,
                "noexcept": noexcept_boundary,
                "trivial_element": trivial_container,
                "ownership_change_permitted": False,
            },
            "hard_hazards": hard_hazards,
            "schedule_hint_eligible": schedule_hint_eligible,
            "escaping_control": escaping_control,
            "closure_mode": closure_mode,
            "boundary": {
                "declared_locals": sorted(declarations),
                "referenced_identifiers": sorted(references),
                "candidate_live_ins": sorted(references - declarations),
            },
            "classification": (
                "effect_preserving_schedule" if hard_hazards and schedule_hint_eligible else
                "blocked" if hard_hazards else
                "bounded_no_growth_container" if bounded_no_growth else
                "structured_multi_exit_candidate" if structured_return_exit else
                "bounded_container_candidate" if capacity else
                "helper_summary_candidate" if helper_summary_closed else
                "helper_closure_candidate" if unmodeled else
                "extractable_local_candidate"
            ),
            # Local extraction and source-preserving scheduling are different
            # closure claims.  A callback, atomic, allocation, or owning loop
            # can safely receive an ordinary Clang schedule request while it
            # is still not a closed lambda/proof capsule.
            "extractable_candidate": (
                not hard_hazards
                and (not escaping_control or structured_return_exit)
            ),
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
    abi: dict[str, Any],
    source: dict[str, Any],
    effects: dict[str, Any],
    subregions: list[dict[str, Any]],
    *,
    function_identity: str = "unknown-cpp-function",
    compiler_identity: str = "clang-cpp-capture",
    function_name: str = "cpp-region",
) -> dict[str, Any]:
    nodes: list[SemanticFlowNode] = []
    edges: list[SemanticFlowEdge] = []
    graph_obligations = []
    for index, parameter in enumerate(abi["parameters"]):
        node_id = f"parameter-{index}"
        item_obligation = obligation(
            f"cpp.abi.parameter.{index}",
            "ownership" if parameter.get("borrowed") else "shape",
            "parameter ownership, extent, and object lifetime match the selected C++ ABI",
            proof_method="clang-ast-abi-and-adapter-proof",
            language="cpp",
            native_construct=str(parameter.get("spelling", "parameter")),
            facts={"ownership": parameter.get("ownership"), "proof_model": parameter.get("proof_model")},
        )
        graph_obligations.append(item_obligation)
        nodes.append(SemanticFlowNode(
            node_id, "Input", "typed-parameter", (), str(parameter.get("spelling", "unknown")),
            {"type_descriptor": parameter}, {"frontend": "clang-semantic-ast"}, (item_obligation,),
        ))
        edges.append(SemanticFlowEdge(
            f"edge.{node_id}", node_id, "compiled-region", str(parameter.get("spelling", "unknown")),
            str(parameter.get("ownership", "unknown")), f"parameter-{index}", "function-call", "sequenced",
            memory_region="argument", validity_scope="selected-call",
        ))

    call_ids = []
    for index, call in enumerate(source["calls"]):
        node_id = f"source-call-{index}"
        disposition = "external_or_summarized" if effects["external_calls"] else "lowered_into_compiled_region"
        nodes.append(SemanticFlowNode(
            node_id, "Call", "call", (), "call-result", {"callee": call, "disposition": disposition},
            {"frontend": "clang-semantic-ast"}, (),
        ))
        edges.append(SemanticFlowEdge(
            f"edge.{node_id}", node_id, "compiled-region", "call-result", "ephemeral", "call",
            "expression", "lowering-provenance",
        ))
        call_ids.append(node_id)
    for region in subregions:
        node_id = region["id"]
        kind = "Loop" if "loop" in str(region.get("classification", "")).lower() else "View"
        nodes.append(SemanticFlowNode(
            node_id, kind, "bounded-source-subregion", (), "region",
            {"source_range": region["source_range"], "classification": region["classification"], "boundary": region["boundary"]},
            {"frontend": "clang-semantic-ast"}, (),
        ))
        edges.append(SemanticFlowEdge(
            f"edge.{node_id}", node_id, "compiled-region", "region", "borrowed", "subregion",
            "function-call", "source-provenance",
        ))

    nodes.append(SemanticFlowNode(
        "compiled-region", "Map", "compiled-cpp-region",
        tuple([f"parameter-{index}" for index in range(len(abi["parameters"]))] + call_ids + [item["id"] for item in subregions]),
        str(abi["return"].get("spelling", "unknown")),
        {"memory_effect": effects["memory_effect"], "instruction_counts": effects["instruction_counts"], "local_effects": effects["local_effects"]},
        {"semantic_ir": "clang-llvm", "source_effects": effects.get("source")}, (),
    ))
    nodes.append(SemanticFlowNode(
        "result", "Output", "typed-result", ("compiled-region",), str(abi["return"].get("spelling", "unknown")),
        {"type_descriptor": abi["return"]}, {"frontend": "clang-semantic-ast"}, (),
    ))
    edges.append(SemanticFlowEdge(
        "edge.result", "compiled-region", "result", str(abi["return"].get("spelling", "unknown")),
        str(abi["return"].get("ownership", "value")), "return", "function-call", "sequenced",
        memory_region="return", validity_scope="caller-observation",
    ))

    typed_effects: list[SemanticEffect] = []
    protocols: list[ProtocolTransition] = []

    def add_obligation(identifier: str, category: str, statement: str, construct: str, method: str = "project-protocol-proof") -> Any:
        item = obligation(identifier, category, statement, proof_method=method, language="cpp", native_construct=construct)
        graph_obligations.append(item)
        return item

    memory_text = str(effects.get("memory_effect", "unknown"))
    if effects["instruction_counts"].get("loads", 0) or "read" in memory_text:
        typed_effects.append(SemanticEffect("cpp.effect.read", "MemoryRead", "execute", "argument-or-object-state", "source-visible-through-result", "program-order", ("compiled-region",), (), {"llvm_memory": memory_text}))
    if effects["instruction_counts"].get("stores", 0) or "write" in memory_text:
        typed_effects.append(SemanticEffect("cpp.effect.write", "MemoryWrite", "execute", "argument-or-object-state", "source-observable", "program-order", ("compiled-region",), (), {"llvm_memory": memory_text}))
    if effects["allocation_calls"]:
        owned = add_obligation("cpp.ownership.allocate", "ownership", "allocation ownership and failure behavior are preserved", "allocation")
        typed_effects.append(SemanticEffect("cpp.effect.allocate", "Allocate", "execute", "heap", "source-observable", "program-order", ("compiled-region",), (owned.id,), {"calls": effects["allocation_calls"]}))
        protocols.append(ProtocolTransition("cpp.protocol.allocate", "Ownership", "unallocated", "allocate", "owned", "allocation-succeeds", (owned.id,), {"mechanism": effects["allocation_calls"]}))
    if effects["deallocation_calls"]:
        retired = add_obligation("cpp.ownership.retire", "cleanup", "destruction and retirement occur after final use", "destructor-or-deallocation")
        typed_effects.extend([
            SemanticEffect("cpp.effect.cleanup", "Cleanup", "exit", "owned-state", "source-observable", "C++ destruction order", ("compiled-region",), (retired.id,), {"calls": effects["deallocation_calls"]}),
            SemanticEffect("cpp.effect.deallocate", "Deallocate", "exit", "heap", "source-observable", "after-cleanup", ("compiled-region",), (retired.id,), {"calls": effects["deallocation_calls"]}),
        ])
        protocols.append(ProtocolTransition("cpp.protocol.retire", "Cleanup", "owned", "scope-exit", "retired", "no-live-readers", (retired.id,), {"mechanism": "destructor/deallocation"}))
    if effects["unwind_operations"] or not effects["nounwind"]:
        unwind = add_obligation("cpp.exception.unwind", "exception", "exceptional exits and cleanup observables are preserved", "throw/invoke/unwind")
        typed_effects.append(SemanticEffect("cpp.effect.exception", "ExceptionalExit", "exit", "exception-state", "source-observable", "C++ unwind order", ("compiled-region",), (unwind.id,), {}))
        protocols.append(ProtocolTransition("cpp.protocol.exception", "Exception", "executing", "throw-or-unwind", "exceptional-exit", "exception-path", (unwind.id,), {"mechanism": "C++ exception"}))
    if effects["synchronization_operations"] or effects["volatile_operations"]:
        sync = add_obligation("cpp.concurrency.order", "concurrency", "atomic, volatile, and synchronization order is preserved", "C++ memory model")
        typed_effects.append(SemanticEffect("cpp.effect.synchronize", "Synchronize", "execute", "shared-state", "inter-thread-observable", "C++ happens-before", ("compiled-region",), (sync.id,), {"volatile": effects["volatile_operations"]}))
        protocols.append(ProtocolTransition("cpp.protocol.synchronize", "Concurrency", "unpublished", "synchronize", "visible", "memory-order-contract", (sync.id,), {"memory_model": "C++"}))
    if effects["external_calls"] or effects["indirect_calls"]:
        external = add_obligation("cpp.external.contract", "external-effect", "external call observables and callback behavior are preserved", "external-or-indirect-call")
        typed_effects.append(SemanticEffect("cpp.effect.external", "ExternalCall", "execute", "external-system", "externally-observable", "call-order", tuple(call_ids) or ("compiled-region",), (external.id,), {"calls": effects["external_calls"], "indirect_count": effects["indirect_calls"]}))
    if source["object_state"]:
        add_obligation("cpp.object.invariant", "state", "reads and writes through this preserve the declared class invariant", "this-object")

    graph = SemanticFlowGraph(
        function_name,
        "cpp",
        compiler_identity,
        "clang-ast-and-llvm",
        function_identity,
        tuple(nodes),
        tuple(edges),
        {"abi": abi, "local_effects": effects["local_effects"], "object_state": source["object_state"]},
        ("arbitrary C++ equivalence", "unmodeled allocator, destructor, concurrency, and external protocols"),
        tuple(graph_obligations),
        tuple(typed_effects),
        tuple(protocols),
    )
    result = graph.to_dict()
    result["graph_sha256"] = graph.graph_hash
    result["invariants"] = {
        "compiler_build_specific": True,
        "source_object_state": source["object_state"],
        "remaining_external_calls": effects["external_calls"],
        "unwind": effects["unwind_operations"],
        "synchronization": effects["synchronization_operations"],
    }
    return result
