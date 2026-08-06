from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any


CPP_PROTOCOL_SCHEMA = "vladder-cpp-protocols-v1"


@dataclass(frozen=True)
class CppContainerState:
    data_identity: str
    size: str
    capacity: str
    allocator_identity: str
    initialized_element_range: str
    element_lifetime_state: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CppCallProtocol:
    id: str
    semantic_class: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    flags: tuple[str, ...]
    normal_postcondition: str
    exceptional_postcondition: str
    crossing: str
    state: dict[str, Any]
    authority: str = "contract"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["summary_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload


def classify_cpp_call(symbol: str) -> CppCallProtocol | None:
    demangled_hint = symbol
    if re.search(
        r"^(?:bcmp|memcmp|memchr|memcpy|memmove|memset|strlen|strnlen|"
        r"__memcpy_chk|__memmove_chk|__memset_chk)$", symbol
    ):
        writes = ("argmem",) if re.search(r"(?:cpy|move|set)", symbol) else ()
        return CppCallProtocol(
            "c-bounded-memory", "bounded-memory-primitive", ("argmem",), writes, (),
            "the selected C library byte relation and return channel are preserved",
            "no exceptional C++ outcome; invalid pointer/extent behavior remains outside the contract",
            "call-preserving-only",
            {"extent_contract": "all accessed byte ranges are valid and non-overlapping where required"},
        )
    if "steady_clock" in symbol and "now" in symbol:
        return CppCallProtocol(
            "monotonic-clock", "time-observation", ("external-clock",), (),
            ("nondeterminism",), "returns one monotonic-clock observation",
            "no C++ exceptional outcome under the selected standard-library ABI",
            "forbidden", {"observable": "clock value and call cardinality/order"},
        )
    container = _container_kind(demangled_hint)
    if container:
        operation = _container_operation(demangled_hint)
        flags: set[str] = set()
        normal = "container state follows the selected standard-library operation"
        exceptional = "the selected library exception guarantee and constructed-element cleanup hold"
        writes = ("argmem", "global-or-heap")
        if operation in {"destroy", "deallocate"}:
            flags.update(("cleanup", "deallocate"))
        elif operation in {"reserve", "grow", "insert", "append", "assign", "resize", "construct"}:
            flags.add("allocate")
            flags.add("unwind")
        elif operation == "read":
            writes = ()
            exceptional = "no exceptional outcome under the selected ABI preconditions"
        return CppCallProtocol(
            f"std-{container}-{operation}",
            "container-state-transition",
            ("argmem", "global-or-heap"),
            writes,
            tuple(sorted(flags)),
            normal,
            exceptional,
            "call-preserving-only",
            {
                "container": container,
                "operation": operation,
                "abstract_state": CppContainerState(
                    "data", "size", "capacity", "allocator", "[0,size)", "constructed"
                ).to_dict(),
                "invalidation": "operation-specific; growth invalidates element addresses",
            },
        )
    if re.search(r"(?:^|_)(?:Zn[aw]|malloc|calloc|realloc|aligned_alloc|allocate)", symbol):
        return CppCallProtocol(
            "allocation", "allocation", (), ("global-or-heap",), ("allocate", "unwind"),
            "returns uniquely owned storage or the declared failure result",
            "no caller-visible allocation remains on failure",
            "call-preserving-only", {"ownership": "caller-on-success"},
        )
    if re.search(r"(?:^|_)(?:Zd[al]|free|deallocate)", symbol):
        return CppCallProtocol(
            "deallocation", "retirement", ("global-or-heap",), ("global-or-heap",),
            ("cleanup", "deallocate"), "owned storage is retired", "not-applicable",
            "call-preserving-only", {"ownership": "consumed"},
        )
    if any(token in symbol for token in ("__cxa_", "__clang_call_terminate", "_Unwind_")):
        return CppCallProtocol(
            "cpp-exception-runtime", "exception-runtime", ("runtime-private",),
            ("runtime-private",), ("cleanup", "unwind"),
            "exception runtime follows the selected C++ ABI",
            "terminate or propagation follows the selected C++ ABI",
            "forbidden", {"abi": "selected-build-exception-personality"},
        )
    if re.search(r"(?:pthread_|mutex|condition_variable|atomic|semaphore|futex)", symbol, re.I):
        return CppCallProtocol(
            "synchronization", "synchronization", ("argmem",), ("argmem",),
            ("synchronize",), "declared happens-before transition completes",
            "failure outcome follows the bound synchronization API",
            "call-preserving-only", {"ordering": "API-contract-required"},
        )
    if re.search(r"(?:^|_)(?:llround|lround|round|floor|ceil|trunc|sqrt|exp|log|sin|cos)", symbol):
        return CppCallProtocol(
            "math-environment", "math-call", ("floating-environment",),
            ("floating-environment",), (), "returns the selected math-library result",
            "domain/range and floating-environment behavior are preserved",
            "call-preserving-only", {"numeric_contract": "selected-library-and-fenv"},
        )
    if symbol.startswith("_ZSt") or "ranges" in symbol:
        return CppCallProtocol(
            "std-algorithm", "bounded-algorithm", ("argmem",), ("argmem",),
            ("unwind",), "algorithm result and required ordering/stability are preserved",
            "callback and element-operation exception behavior is preserved",
            "call-preserving-only", {"callback_contract": "finite callable summary required"},
        )
    return None


def exceptional_cfg_summary(body: str) -> dict[str, Any]:
    blocks = _basic_blocks(body)
    invokes = []
    cleanup_blocks: list[dict[str, Any]] = []
    for name, lines in blocks.items():
        joined = "\n".join(lines)
        for match in re.finditer(
            r"\binvoke\b.*?\bto\s+label\s+%([-A-Za-z$._0-9]+)\s+unwind\s+label\s+%([-A-Za-z$._0-9]+)",
            joined,
        ):
            invokes.append({"block": name, "normal": match.group(1), "unwind": match.group(2)})
        if re.search(r"\b(?:landingpad|catchswitch|catchpad|cleanuppad)\b", joined):
            calls = re.findall(r'\bcall\b[^@]*@(?:"([^"]+)"|([-A-Za-z$._0-9]+))', joined)
            cleanup_blocks.append({
                "block": name,
                "kind": (
                    "terminate" if "__clang_call_terminate" in joined else
                    "resume" if re.search(r"\bresume\b", joined) else
                    "cleanup"
                ),
                "calls": [left or right for left, right in calls],
                "resumes": bool(re.search(r"\bresume\b", joined)),
            })
    return {
        "schema_version": CPP_PROTOCOL_SCHEMA,
        "invokes": invokes,
        "cleanup_blocks": cleanup_blocks,
        "normal_exit_count": len(re.findall(r"^\s*ret\b", body, re.MULTILINE)),
        "resume_count": len(re.findall(r"^\s*resume\b", body, re.MULTILINE)),
        "terminate_calls": len(re.findall(r"@__clang_call_terminate\b", body)),
        "outcome_observable": "return-or-exception+committed-state+cleanup-trace+external-effects",
    }


def memory_order_summary(body: str) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\b(load\s+atomic|store\s+atomic|atomicrmw|cmpxchg|fence)\b([^\n]*)"
    )
    orderings = ("unordered", "monotonic", "acquire", "release", "acq_rel", "seq_cst")
    for ordinal, match in enumerate(pattern.finditer(body)):
        tail = match.group(2)
        found = [ordering for ordering in orderings if re.search(rf"\b{ordering}\b", tail)]
        syncscope = re.search(r'syncscope\("([^"]+)"\)', tail)
        operations.append({
            "id": f"atomic.{ordinal}",
            "operation": match.group(1),
            "orderings": found,
            "sync_scope": syncscope.group(1) if syncscope else "system",
            "publication_capable": any(item in {"release", "acq_rel", "seq_cst"} for item in found),
            "acquisition_capable": any(item in {"acquire", "acq_rel", "seq_cst"} for item in found),
        })
    volatile = [
        {"id": f"volatile.{index}", "operation": match.group(1), "ordering": "program-order-observable"}
        for index, match in enumerate(re.finditer(r"\b(load|store)\s+volatile\b", body))
    ]
    return {
        "schema_version": CPP_PROTOCOL_SCHEMA,
        "atomic_operations": operations,
        "volatile_operations": volatile,
        "requires_happens_before_contract": bool(operations),
        "requires_external_observation_order": bool(volatile),
    }


def object_state_projection(body: str, signature: str) -> dict[str, Any]:
    argument_match = re.search(r"\(([^)]*)\)", signature)
    first_pointer = None
    if argument_match:
        pointer = re.search(r"\bptr\b[^,%)]*\s+(%[-A-Za-z$._0-9]+)", argument_match.group(1))
        first_pointer = pointer.group(1) if pointer else None
    projections: list[dict[str, Any]] = []
    if first_pointer:
        pattern = re.compile(
            rf"(%[-A-Za-z$._0-9]+)\s*=\s*getelementptr\b([^\n]*?\bptr\s+{re.escape(first_pointer)}\b[^\n]*)"
        )
        for match in pattern.finditer(body):
            value_id, expression = match.groups()
            indices = re.findall(r"\bi(?:32|64)\s+(-?\d+)", expression)
            uses = "\n".join(
                line for line in body.splitlines() if re.search(rf"\b{re.escape(value_id)}\b", line)
            )
            projections.append({
                "pointer": value_id,
                "indices": [int(value) for value in indices],
                "read": bool(re.search(rf"\bload\b[^\n]*\bptr\s+{re.escape(value_id)}\b", uses)),
                "written": bool(re.search(rf"\bstore\b[^\n]*,\s*ptr\s+{re.escape(value_id)}\b", uses)),
                "channel": "llvm-gep-offset-projection",
            })
    return {
        "schema_version": CPP_PROTOCOL_SCHEMA,
        "this_argument": first_pointer,
        "projections": projections,
        "old_new_relation": bool(projections),
        "preservation_contract": "all unlisted object storage remains unchanged",
    }


def _container_kind(symbol: str) -> str | None:
    checks = (
        ("vector", ("St6vector", "std::vector")),
        ("deque", ("St5deque", "std::deque")),
        ("string", ("basic_string", "__cxx11", "std::string")),
    )
    for kind, tokens in checks:
        if any(token in symbol for token in tokens):
            return kind
    return None


def _container_operation(symbol: str) -> str:
    checks = (
        ("destroy", ("D0Ev", "D1Ev", "D2Ev", "~")),
        ("reserve", ("reserve", "7reserve")),
        ("resize", ("resize", "6resize")),
        ("insert", ("insert", "_M_realloc_insert", "_M_range_insert")),
        ("append", ("push_back", "emplace_back")),
        ("assign", ("assign", "aSER", "_M_assign", "_M_replace", "_M_mutate")),
        ("construct", ("C1E", "C2E")),
        ("read", ("size", "capacity", "data", "begin", "end")),
    )
    for operation, tokens in checks:
        if any(token in symbol for token in tokens):
            return operation
    return "mutation"


def _basic_blocks(body: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {"entry": []}
    current = "entry"
    for line in body.splitlines():
        match = re.match(r"^([-A-Za-z$._0-9]+):", line)
        if match:
            current = match.group(1)
            blocks.setdefault(current, [])
        else:
            blocks[current].append(line)
    return blocks
