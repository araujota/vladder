from __future__ import annotations

import hashlib
import re
from typing import Any

from .protocol_envelopes import match_protocol_envelope
from .semantic_closure import CallRelation, EffectFootprint, FunctionSummary


CLOSURE_BINDINGS_SCHEMA = "semantic-closure-bindings-v1"


def _system_identity(language: str, native_identity: str) -> str:
    return f"{language}::{native_identity}"


def language_boundary_catalog() -> dict[str, Any]:
    shared = [
        {
            "boundary": "definition-visible direct calls",
            "disposition": "compositional_summary",
            "closure": "decisively_closable",
            "search_effect": "none; relation constrains legality",
        },
        {
            "boundary": "finite aggregate results and ordinary multi-exit control",
            "disposition": "aggregate/tagged-exit envelope",
            "closure": "decisively_closable",
            "search_effect": "none until a computational grammar consumes the channels",
        },
        {
            "boundary": "borrowed views and checked no-growth contiguous output",
            "disposition": "ownership envelope with guards",
            "closure": "decisively_closable_under_explicit_capacity/lifetime facts",
            "search_effect": "none; guards filter candidates",
        },
        {
            "boundary": "arbitrary callback, open indirect dispatch, undeclared third-party API",
            "disposition": "local opaque protocol boundary",
            "closure": "categorically_requires_external_contract",
            "search_effect": "closed neighboring subgraphs remain searchable",
        },
        {
            "boundary": "concurrent publication, external I/O, driver/runtime protocol",
            "disposition": "bounded protocol model or boundary-preserving call",
            "closure": "closable_only_for_declared_finite_protocol",
            "search_effect": "protocol states are verified separately, not enumerated as local rewrites",
        },
    ]
    languages = {
        "c": [
            "LLVM memory attributes and direct helpers close compositionally",
            "function pointers require a finite target set",
            "volatile, atomics, syscalls, and implementation-defined ABI behavior require explicit contracts",
        ],
        "cpp": [
            "trivial aggregates, spans, borrowed vectors, checked no-growth append, and finite CFG exits close",
            "nontrivial RAII and allocation close only through declared ownership/cleanup envelopes",
            "virtual dispatch, exceptions crossing the region, coroutines, and external object protocols remain scoped",
        ],
        "rust": [
            "borrowed slices and monomorphized MIR helpers close",
            "Drop and panic cleanup bind to cleanup/unwind envelopes",
            "trait objects, async executors, unsafe contracts, FFI, and concurrent runtimes remain scoped without finite models",
        ],
        "zig": [
            "slices, optionals/tagged results, error exits, and defer cleanup bind to shared envelopes",
            "allocator ownership closes only with finite success/failure and retirement paths",
            "async, volatile, atomics, inline assembly, FFI, and arbitrary callbacks remain scoped without contracts",
        ],
        "julia": [
            "one concrete typed specialization, isbits aggregates, bounds exits, and inferred direct invokes can close",
            "GC allocation and escape require ownership/retention scope and captured world identity",
            "dynamic dispatch, tasks, mutable globals, ccall, and future world states remain scoped without finite models",
        ],
    }
    return {
        "schema_version": CLOSURE_BINDINGS_SCHEMA,
        "shared_boundaries": shared,
        "languages": languages,
        "semantic_vocabulary": "shared SemanticFlowGraph v2 + EffectFootprint + protocol envelopes",
    }


def _memory_regions(memory_effect: str) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    normalized = memory_effect.replace(" ", "").lower()
    if normalized in {"none", "readnone"}:
        return (), (), False
    reads: set[str] = set()
    writes: set[str] = set()
    unknown = normalized in {"", "unknown"}
    mappings = {
        "argmem": "argmem",
        "inaccessiblemem": "runtime-private",
        "other": "global-or-heap",
        "memory": "unknown-memory",
    }
    for native, canonical in mappings.items():
        if native in normalized:
            if "read" in normalized:
                reads.add(canonical)
            if "write" in normalized:
                writes.add(canonical)
    if not reads and not writes and normalized not in {"none", "readnone"}:
        if "readonly" in normalized or normalized == "read":
            reads.add("unknown-memory")
        elif "writeonly" in normalized or normalized == "write":
            writes.add("unknown-memory")
        elif "readwrite" in normalized or "modref" in normalized:
            reads.add("unknown-memory")
            writes.add("unknown-memory")
        else:
            unknown = True
    return tuple(reads), tuple(writes), unknown


def cpp_effect_footprint(effects: dict[str, Any]) -> EffectFootprint:
    reads, writes, unknown = _memory_regions(str(effects.get("memory_effect", "unknown")))
    flags = set()
    if effects.get("allocation_calls"):
        flags.add("allocate")
    if effects.get("deallocation_calls"):
        flags.add("deallocate")
    if effects.get("unwind_operations") or not effects.get("nounwind", False):
        flags.add("unwind")
    if effects.get("synchronization_operations"):
        flags.add("synchronize")
    if effects.get("volatile_operations"):
        flags.add("volatile")
    if effects.get("global_stores"):
        writes = tuple(sorted(set(writes) | {"global-or-heap"}))
    if effects.get("indirect_calls"):
        flags.add("callback")
        unknown = True
    if effects.get("external_calls"):
        flags.add("external_io")
        unknown = True
    return EffectFootprint(reads, writes, tuple(flags), unknown)


def cpp_function_summary(
    function: str,
    compiler_identity: str,
    effects: dict[str, Any],
    *,
    semantic_graph_hash: str = "",
    candidate_count: int = 0,
    source_language: str = "cpp",
    semantic_capture: str | None = None,
    residual_boundaries: tuple[dict[str, Any], ...] = (),
) -> FunctionSummary:
    identity = _system_identity(source_language, function)
    calls = []
    internal = effects.get("internal_call_summaries", {})
    declared = effects.get("declared_call_summaries", {})
    protocols = effects.get("protocol_call_summaries", {})
    external = set(effects.get("external_calls", []))
    for index, target in enumerate(effects.get("remaining_direct_calls", [])):
        if target in declared and target not in external:
            summary = declared[target]
            reads, writes, unknown = _memory_regions(str(summary.get("memory_effect", "unknown")))
            calls.append(CallRelation(
                f"{identity}.call.{index}", identity, (), "intrinsic", target,
                EffectFootprint(reads, writes, (), unknown),
                authority="compiler-attribute", crossing="call-preserving-only",
                provenance={
                    "language": "cpp",
                    "native_construct": target,
                    "summary_sha256": summary.get("summary_sha256"),
                    "next_action": "retain the exact call; crossing it requires a functional proof",
                },
            ))
        elif target in internal and target not in external:
            summary = internal[target]
            reads, writes, unknown = _memory_regions(str(summary.get("memory_effect", "unknown")))
            relation_effects = EffectFootprint(
                reads, writes,
                ("unwind",) if not summary.get("nounwind", False) else (),
                unknown,
            )
            calls.append(CallRelation(
                f"{identity}.call.{index}", identity, (_system_identity(source_language, target),), "definition", target,
                relation_effects, authority="definition-hash", crossing="call-preserving-only",
                provenance={
                    "language": "cpp",
                    "native_construct": target,
                    "body_sha256": summary.get("function_body_sha256"),
                    "next_action": "inline the helper or prove a functional relation before crossing the call",
                },
            ))
        elif target in protocols and target not in external:
            summary = protocols[target]
            calls.append(CallRelation(
                f"{identity}.call.{index}", identity, (), "protocol", target,
                EffectFootprint(
                    tuple(summary.get("reads", ())),
                    tuple(summary.get("writes", ())),
                    tuple(summary.get("flags", ())),
                    False,
                ),
                authority=str(summary.get("authority", "language/library-contract")),
                crossing=str(summary.get("crossing", "call-preserving-only")),
                protocol=str(summary.get("id", "language-library-protocol")),
                provenance={
                    "language": "cpp",
                    "native_construct": target,
                    "protocol": summary.get("id"),
                    "semantic_class": summary.get("semantic_class"),
                    "summary_sha256": summary.get("summary_sha256"),
                    "normal_postcondition": summary.get("normal_postcondition"),
                    "exceptional_postcondition": summary.get("exceptional_postcondition"),
                    "next_action": "retain the protocol call or prove a functional relation before crossing it",
                },
            ))
        else:
            calls.append(CallRelation(
                f"{identity}.call.{index}", identity, (_system_identity(source_language, target),), "opaque", target,
                EffectFootprint(flags=("external_io",), unknown=True),
                authority="opaque", crossing="forbidden",
                provenance={
                    "language": "cpp",
                    "native_construct": target,
                    "missing_contract": "definition-visible body or declared external protocol relation",
                },
            ))
    if effects.get("indirect_calls"):
        calls.append(CallRelation(
            f"{identity}.indirect", identity, (), "opaque", "indirect-call",
            EffectFootprint(flags=("callback",), unknown=True), authority="opaque", crossing="forbidden",
            provenance={
                "language": "cpp",
                "native_construct": "function pointer, virtual dispatch, or callback",
                "missing_contract": "finite target set and per-target effect/functional summaries",
            },
        ))
    return FunctionSummary(
        identity, source_language, compiler_identity,
        str(effects.get("function_body_sha256", "")), semantic_graph_hash,
        cpp_effect_footprint(effects), tuple(calls), candidate_count,
        {
            "schema_version": CLOSURE_BINDINGS_SCHEMA,
            "semantic_capture": semantic_capture or ("closed" if effects.get("local_effects") else "partial"),
            "residual_boundaries": list(residual_boundaries),
            "native_attributes": effects.get("attributes", ""),
            "protocol_envelopes": list(match_protocol_envelope((
                *effects.get("allocation_calls", ()), *effects.get("deallocation_calls", ()),
                "multiple return" if effects.get("instruction_counts", {}).get("returns", 0) > 1 else "",
            ))),
        },
    )


def rust_effect_footprint(summary: Any) -> EffectFootprint:
    flags = set()
    unknown = False
    if not summary.allocation_free:
        flags.update(("allocate", "deallocate"))
    if not summary.panic_free_under_contract:
        flags.add("unwind")
    if not summary.custom_drop_free:
        flags.add("cleanup")
    if not summary.concurrency_free:
        flags.update(("synchronize", "atomic"))
    if not summary.ffi_free:
        flags.add("external_io")
        unknown = True
    if summary.unresolved_calls:
        unknown = True
    return EffectFootprint(("argmem",), ("argmem",), tuple(flags), unknown)


def rust_function_summary(
    function: Any,
    effects: Any,
    compiler_identity: str,
    *,
    semantic_graph_hash: str = "",
    candidate_count: int = 0,
    blockers: tuple[dict[str, Any], ...] | None = None,
) -> FunctionSummary:
    identity = _system_identity("rust", function.qualified_name)
    calls = []
    for index, target in enumerate(effects.unresolved_calls):
        calls.append(CallRelation(
            f"{identity}.call.{index}", identity, (_system_identity("rust", target),), "opaque", target,
            EffectFootprint(flags=("callback",), unknown=True), authority="opaque", crossing="forbidden",
            provenance={
                "language": "rust", "native_construct": target,
                "missing_contract": "monomorphized MIR body or declared trait/FFI relation",
            },
        ))
    constructs = [parameter.type for parameter in function.parameters]
    if not effects.custom_drop_free:
        constructs.append("Drop")
    if not effects.allocation_free:
        constructs.append("allocator")
    residual = tuple(effects.blockers) if blockers is None else blockers
    return FunctionSummary(
        identity, "rust", compiler_identity, function.function_sha256,
        semantic_graph_hash, rust_effect_footprint(effects), tuple(calls), candidate_count,
        {
            "schema_version": CLOSURE_BINDINGS_SCHEMA,
            "semantic_capture": "closed" if not residual else "partial",
            "residual_boundaries": list(residual),
            "protocol_envelopes": list(match_protocol_envelope(constructs)),
            "panic_contract": "panic paths and MIR cleanup remain observable unless proved unreachable",
        },
    )


def zig_effect_footprint(function_source: str) -> EffectFootprint:
    flags = set()
    reads = {"argmem"}
    writes = set()
    unknown = False
    if re.search(r"\b(?:allocator\.|alloc\s*\(|create\s*\()", function_source):
        flags.add("allocate")
    if re.search(r"\b(?:free\s*\(|destroy\s*\()", function_source):
        flags.add("deallocate")
    if re.search(r"\b(?:defer|errdefer)\b", function_source):
        flags.add("cleanup")
    if re.search(r"\b(?:try|catch|error\{|!\[|!usize)\b", function_source):
        flags.add("unwind")
    if re.search(r"\b(?:@atomic|@cmpxchg|std\.atomic)\b", function_source):
        flags.update(("atomic", "synchronize"))
    if re.search(r"\bvolatile\b|\*volatile", function_source):
        flags.add("volatile")
    if re.search(r"\b(?:@cImport|callconv\(\.C\)|extern\s+fn|asm\s*)\b", function_source):
        flags.add("external_io")
        unknown = True
    if re.search(r"\basync\b|\bawait\b|\bsuspend\b|\bresume\b", function_source):
        flags.update(("synchronize", "nondeterminism"))
    if re.search(r"\[[^]]+\]\s*=|\.\*\s*=", function_source):
        writes.add("argmem")
    return EffectFootprint(tuple(reads), tuple(writes), tuple(flags), unknown)


def zig_function_summary(
    function: str,
    function_source: str,
    compiler_identity: str,
    *,
    semantic_graph_hash: str = "",
    candidate_count: int = 0,
    blockers: tuple[dict[str, Any], ...] = (),
) -> FunctionSummary:
    constructs = re.findall(
        r"\b(?:defer|errdefer|try|catch|allocator|alloc|free|error union|extern fn|volatile|@atomic)\b",
        function_source,
    )
    return FunctionSummary(
        _system_identity("zig", function), "zig", compiler_identity, hashlib.sha256(function_source.encode()).hexdigest(),
        semantic_graph_hash, zig_effect_footprint(function_source), (), candidate_count,
        {
            "schema_version": CLOSURE_BINDINGS_SCHEMA,
            "semantic_capture": "closed" if not blockers else "partial",
            "residual_boundaries": list(blockers),
            "protocol_envelopes": list(match_protocol_envelope(constructs)),
            "error_contract": "error returns are tagged exits; defer/errdefer cleanup ordering remains observable",
        },
    )


def julia_effect_footprint(
    typed_ir: str,
    llvm_ir: str,
    *,
    allocated_bytes: int | None,
) -> EffectFootprint:
    combined = typed_ir + "\n" + llvm_ir
    flags = set()
    unknown = False
    if allocated_bytes is None or allocated_bytes > 0 or "jl_gc_alloc" in combined:
        flags.add("allocate")
    if re.search(r"\b(?:throw|jl_throw|bounds_error|error)\b", combined, re.I):
        flags.add("unwind")
    if re.search(r"\b(?:@async|@spawn|Threads\.|jl_task|atomic)\b", combined):
        flags.update(("synchronize", "nondeterminism"))
    if re.search(r"\b(?:ccall|@ccall|llvmcall|foreigncall)\b", combined):
        flags.add("external_io")
        unknown = True
    if re.search(r"\b(?:setglobal!|globalref|@eval|Core\.eval)\b", combined, re.I):
        flags.update(("publish", "invalidate"))
    return EffectFootprint(("argmem",), ("argmem",), tuple(flags), unknown)


def julia_function_summary(
    function: str,
    signature: str,
    compiler_identity: str,
    typed_ir: str,
    llvm_ir: str,
    *,
    world: str,
    allocated_bytes: int | None,
    semantic_graph_hash: str = "",
    candidate_count: int = 0,
    blockers: tuple[dict[str, Any], ...] = (),
) -> FunctionSummary:
    body_hash = hashlib.sha256((typed_ir + "\n" + llvm_ir).encode()).hexdigest()
    constructs = [
        "gc allocation" if allocated_bytes is None or allocated_bytes > 0 else "",
        "isbits aggregate" if re.search(r"isbits|\{[^}]+\}", typed_ir, re.I) else "",
    ]
    return FunctionSummary(
        _system_identity("julia", f"{function}::{signature}"), "julia", compiler_identity, body_hash,
        semantic_graph_hash,
        julia_effect_footprint(typed_ir, llvm_ir, allocated_bytes=allocated_bytes),
        (), candidate_count,
        {
            "schema_version": CLOSURE_BINDINGS_SCHEMA,
            "semantic_capture": "closed" if not blockers else "partial",
            "residual_boundaries": list(blockers),
            "world": world,
            "protocol_envelopes": list(match_protocol_envelope(constructs)),
            "specialization_scope": "one concrete method instance and captured world",
        },
    )
