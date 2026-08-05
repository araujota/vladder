from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ADAPTER_SCHEMA = "vladder-cpp-application-adapter-v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def generate_cpp_adapter_bundle(report_path: Path, output_directory: Path) -> dict[str, Any]:
    """Generate an explicit, incomplete application boundary from C++ closure evidence.

    The bundle is intentionally not a generic input generator. It turns every missing semantic
    fact into a named blocker and a concrete hook that an application agent must implement.
    """
    report_path = report_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    report = json.loads(report_path.read_text())
    closure = report.get("closure", {})
    selection = report.get("selection", {})
    typed_abi = report.get("typed_abi", {})
    compile_command = report.get("compile_command", {})
    capabilities = closure.get("capabilities", {})
    protocol_scopes = closure.get("protocol_scopes", [])
    subregions = closure.get("regions", [])
    state_projection = _infer_state_projection(report)
    protocol_inventory = _protocol_inventory(report)

    unresolved: list[dict[str, Any]] = []
    for adapter in report.get("adapters", []):
        unresolved.append({
            "kind": adapter.get("kind", "unknown"),
            "reason": adapter.get("reason", "unreported"),
            "required_boundary": adapter.get("required_boundary", "explicit semantic adapter"),
            "next_workflow": adapter.get("next_workflow", "manual contract"),
        })
    for scope in protocol_scopes:
        unresolved.append({
            "kind": scope.get("category", "external_protocol"),
            "reason": scope.get("evidence", "state absent from local IR"),
            "required_boundary": scope.get("required_adapter", "explicit protocol model"),
            "next_workflow": scope.get("next_workflow", "protocol adapter"),
        })
    if not capabilities.get("benchmark", {}).get("actual"):
        unresolved.append({
            "kind": "application-workload-adapter",
            "reason": "vLadder has no production input constructor, observable oracle, or representative workload",
            "required_boundary": "same-executable baseline/candidate harness with complete observables",
            "next_workflow": "complete benchmark_adapter.cpp and run vladder benchmark paired",
        })

    manifest = {
        "schema_version": ADAPTER_SCHEMA,
        "source_report": str(report_path),
        "source_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "source": report.get("source"),
        "source_sha256": report.get("source_sha256"),
        "function": report.get("function"),
        "selected_symbol": selection.get("symbol"),
        "selected_type": selection.get("type"),
        "compile_command_sha256": compile_command.get("command_sha256"),
        "typed_abi": typed_abi,
        "inferred_state_projection": state_projection,
        "protocol_inventory": protocol_inventory,
        "closure_disposition": closure.get("disposition", "unclassified"),
        "local_proof_classification": report.get("proof_classification", "unclassified"),
        "claim_boundary": report.get("claim_boundary"),
        "application_contract": {
            "input_factory": "TODO_REQUIRED",
            "baseline_entry": "TODO_REQUIRED",
            "candidate_entry": "TODO_REQUIRED",
            "observable_projection": "TODO_REQUIRED",
            "state_projection": "TODO_REQUIRED" if any(
                item.get("category") == "class_state_and_invariant" for item in protocol_scopes
            ) else "not_required_by_current_closure",
            "error_and_exception_projection": "TODO_REQUIRED" if any(
                item.get("category") == "exception_and_destructor_protocol" for item in protocol_scopes
            ) else "not_required_by_current_closure",
            "workload_identity": "TODO_REQUIRED",
            "minimum_effect_percent": 1.0,
            "exact_observables": True,
        },
        "eligible_local_regions": [item.get("id") for item in subregions if item.get("eligible")],
        "unresolved_boundaries": unresolved,
        "promotion_blocked": bool(unresolved),
        "generated_bundle_is_proof": False,
        "bundle_hash": "",
    }
    manifest["bundle_hash"] = _hash({key: value for key, value in manifest.items() if key != "bundle_hash"})
    manifest_path = output_directory / "adapter-manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    benchmark_source = _benchmark_skeleton(manifest)
    oracle_source = _oracle_skeleton(manifest)
    benchmark_path = output_directory / "benchmark_adapter.cpp"
    oracle_path = output_directory / "observable_oracle.cpp"
    benchmark_path.write_text(benchmark_source)
    oracle_path.write_text(oracle_source)
    state_template_path = output_directory / "state-protocol-template.yaml"
    state_template_path.write_text(yaml.safe_dump({
        "schema_version": "vladder-state-protocol-template-v1",
        "protocol": "TODO_REQUIRED_choose_versioned_cache_or_transactional_publication",
        "authoritative_state_fields": state_projection["fields"],
        "mutations": ["TODO_REQUIRED"],
        "invalidators": ["TODO_REQUIRED"],
        "non_invalidators": ["TODO_REQUIRED"],
        "policy": {
            "publish_atomic": "TODO_REQUIRED",
            "retire_after_readers": "TODO_REQUIRED",
        },
        "claim_boundary": "inferred field names are candidates only; the application contract must establish authority and mutation completeness",
    }, sort_keys=False))
    task_path = output_directory / "AGENT_ADAPTER.md"
    task_path.write_text(_agent_task(manifest))

    result = {
        "schema_version": "vladder-cpp-adapter-bundle-result-v1",
        "status": "adapter_skeleton_generated",
        "promotion_ready": False,
        "proof_scope": "none; generated source is an explicit application integration skeleton",
        "manifest": str(manifest_path),
        "benchmark_adapter": str(benchmark_path),
        "observable_oracle": str(oracle_path),
        "state_protocol_template": str(state_template_path),
        "agent_task": str(task_path),
        "unresolved_count": len(unresolved),
        "unresolved_boundaries": unresolved,
        "next_action": "resolve every adapter-manifest TODO, compile the same-executable harness, then run paired measurement",
    }
    _write_json(output_directory / "adapter-bundle.json", result)
    return result


def _walk_ast(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_ast(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_ast(value)


def _infer_state_projection(report: dict[str, Any]) -> dict[str, Any]:
    selected = report.get("artifacts", {}).get("selected_ast")
    fields: dict[tuple[str, str], dict[str, Any]] = {}
    if selected and Path(selected).exists():
        ast = json.loads(Path(selected).read_text())
        for node in _walk_ast(ast):
            if node.get("kind") != "MemberExpr" or not node.get("name"):
                continue
            spelling = str(node["name"])
            qual_type = str(node.get("type", {}).get("qualType", "unknown"))
            fields[(spelling, qual_type)] = {
                "name": spelling,
                "type": qual_type,
                "access": "candidate_read_or_write",
                "authority_status": "requires_application_confirmation",
            }
    return {
        "method": "selected Clang AST MemberExpr inventory",
        "fields": list(fields.values()),
        "complete_class_invariant": False,
        "limitations": [
            "field occurrence does not establish read/write direction, authority, aliasing, or invariant",
            "indirect state reached through pointers or external calls requires a protocol adapter",
        ],
    }


def _protocol_inventory(report: dict[str, Any]) -> dict[str, Any]:
    effects = report.get("compiled_effects", {})
    source = report.get("source_semantics", {})
    return {
        "external_calls": sorted(str(item) for item in effects.get("external_calls", [])),
        "allocation_calls": sorted(str(item) for item in effects.get("allocation_calls", [])),
        "deallocation_calls": sorted(str(item) for item in effects.get("deallocation_calls", [])),
        "source_calls": sorted(str(item) for item in source.get("calls", [])),
        "object_state": bool(source.get("object_state")),
        "can_unwind": not bool(effects.get("nounwind")),
        "synchronization": bool(effects.get("synchronization_operations")),
        "claim": "inventory only; summaries are not protocol semantics",
    }


def _benchmark_skeleton(manifest: dict[str, Any]) -> str:
    symbol = manifest.get("selected_symbol") or "<unselected-symbol>"
    return f'''// Generated by vLadder. This is an application adapter, not proof evidence.
// Selected production symbol: {symbol}
#include <cstdint>
#include <cstdio>
#include <string_view>

namespace vladder_adapter {{
struct Observation {{
    std::uint64_t exact_hash;
    double metric;
}};

// TODO: Construct production-faithful inputs and all owning state.
// TODO: Route baseline and candidate through the same executable and equivalent setup.
// TODO: Include status, exceptions, mutations, outputs, and external effects in exact_hash.
Observation run_variant(std::string_view variant) {{
    (void)variant;
    return {{0, 0.0}};
}}
}}  // namespace vladder_adapter

int main(int argc, char **argv) {{
    if (argc != 2) {{
        std::fprintf(stderr, "usage: benchmark_adapter baseline|candidate\\n");
        return 2;
    }}
    const auto observation = vladder_adapter::run_variant(argv[1]);
    std::printf("{{\\\"metric\\\":%.17g,\\\"observable_hash\\\":\\\"%016llx\\\"}}\\n",
                observation.metric, static_cast<unsigned long long>(observation.exact_hash));
    return observation.exact_hash == 0 ? 3 : 0;  // Fail until the oracle is implemented.
}}
'''


def _oracle_skeleton(manifest: dict[str, Any]) -> str:
    function = manifest.get("function") or "unselected"
    return f'''// Observable projection for {function}.
// Complete this file before treating application differential execution as passing.
#include <cstdint>

namespace vladder_adapter {{
struct ObservableState;

std::uint64_t hash_complete_observable_state(const ObservableState &) {{
    // TODO: Hash every contract-observable output, status, state transition, and external effect.
    return 0;
}}
}}  // namespace vladder_adapter
'''


def _agent_task(manifest: dict[str, Any]) -> str:
    unresolved = "\n".join(
        f"- `{item['kind']}`: {item['reason']} Required: {item['required_boundary']}"
        for item in manifest["unresolved_boundaries"]
    ) or "- No closure blocker was reported; the workload and observable oracle still require review."
    return f"""# vLadder Application Adapter Task

Selected symbol: `{manifest.get('selected_symbol')}`

Local proof classification: `{manifest.get('local_proof_classification')}`

This bundle is not proof and is not promotable. It converts closure metadata into an explicit
application task. Do not weaken the production ABI, state, exception, ordering, ownership, or
external-effect contract to make the harness easier.

## Unresolved Boundaries

{unresolved}

## Required Completion

1. Implement production-faithful input and owner construction in `benchmark_adapter.cpp`.
2. Implement a complete observable projection in `observable_oracle.cpp`.
3. Keep baseline and candidate in the same executable and randomize invocation order.
4. Add high-churn, failure, empty, boundary, and representative production cases.
5. For class state, provide a finite state projection and run `vladder protocol verify`.
6. Run project tests and composed-system benchmarks after local paired measurement.
7. Update the promotion summary; generation of this bundle is not candidate proof.
"""
