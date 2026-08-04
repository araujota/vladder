from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .lifetime_grammar import LifetimeCandidate
from .lifetime_graph import LifetimeFlowGraph
from .lifetime_verification import LifetimeVerificationResult


@dataclass(frozen=True)
class AgentRealizationContract:
    schema_version: str
    candidate_id: str
    information_id: str
    status: str
    current_realization: dict[str, Any]
    target_realization: dict[str, Any]
    semantic_source: tuple[str, ...]
    ownership: dict[str, Any]
    invalidation_matrix: tuple[dict[str, Any], ...]
    lifecycle_hooks: tuple[str, ...]
    permitted_files: tuple[str, ...]
    fallback: str
    debug_oracle: dict[str, Any]
    proof_requirements: tuple[str, ...]
    protocol_adapter_requirements: tuple[str, ...]
    lower_level_handoff: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    source_regeneration: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_agent_realization_contract(
    graph: LifetimeFlowGraph,
    candidate: LifetimeCandidate,
    verification: LifetimeVerificationResult,
) -> AgentRealizationContract:
    item = graph.item(candidate.information_id)
    implementation = item.implementation
    permitted_files = tuple(str(path) for path in implementation.get("permitted_files", ()))
    hooks = tuple(str(hook) for hook in implementation.get("lifecycle_hooks", ()))
    adapters: list[str] = []
    if verification.protocol_adapter:
        adapters.append(verification.protocol_adapter)
    if candidate.candidate_placement.startswith("gpu") or candidate.candidate_placement in {"presentation_image", "device_resident"}:
        adapters.append("GPU ownership, barrier, device-loss, and retirement adapter")
    if item.current.consistency not in {"immutable", "single_threaded"}:
        adapters.append("publication and reader-retirement protocol review")
    matrix = tuple(
        {"mutation": mutation, "action": "invalidate_or_refresh" if mutation in candidate.invalidators else "preserve"}
        for mutation in item.mutations
    )
    status = "ready_for_agent_realization" if verification.status == "PASS" and permitted_files and hooks else "adapter_required"
    return AgentRealizationContract(
        "vladder-agent-lifetime-realization-v1",
        candidate.candidate_id,
        item.id,
        status,
        {
            "scope": candidate.original_scope,
            "placement": candidate.original_placement,
            "construction": item.current.construction,
        },
        {
            "scope": candidate.candidate_scope,
            "placement": candidate.candidate_placement,
            "construction": candidate.construction_policy,
            "mode": candidate.mode,
        },
        item.source,
        {"owner": item.owner, "readers": item.readers, "writers": item.writers, "consistency": item.current.consistency},
        matrix,
        hooks,
        permitted_files,
        candidate.fallback,
        {
            "mode": "sampled_shadow_recompute",
            "comparison": "exact semantic projection",
            "retain_until": "candidate acceptance and production soak",
        },
        candidate.proof_obligations,
        tuple(dict.fromkeys(adapters)),
        candidate.lower_level_families,
        (
            "invent undeclared invariants",
            "omit mutation or retirement paths",
            "silently add global state",
            "remove fallback before acceptance",
            "claim Alive2 lifecycle proof",
            "promote without end-to-end benchmark",
        ),
        "agent_adapter_required; generic repository source emission is not claimed",
    )


def write_agent_realization_bundle(
    output_directory: Path,
    contract: AgentRealizationContract,
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "realization-contract.json"
    prompt_path = output_directory / "AGENT_REALIZATION.md"
    json_path.write_text(json.dumps(contract.to_dict(), indent=2, sort_keys=True) + "\n")
    prompt_path.write_text(_prompt(contract))
    return json_path, prompt_path


def _prompt(contract: AgentRealizationContract) -> str:
    files = "\n".join(f"- `{path}`" for path in contract.permitted_files) or "- No files declared; stop and request an adapter."
    invalidation = "\n".join(
        f"- `{item['mutation']}`: `{item['action']}`" for item in contract.invalidation_matrix
    )
    lower = ", ".join(f"`{family}`" for family in contract.lower_level_handoff)
    return f"""# vLadder Lifetime Realization

Implement candidate `{contract.candidate_id}` for information `{contract.information_id}`.

Current: `{contract.current_realization['scope']}` at `{contract.current_realization['placement']}`.
Target: `{contract.target_realization['scope']}` at `{contract.target_realization['placement']}` using
`{contract.target_realization['mode']}`.

## Permitted Files

{files}

## Invalidation Matrix

{invalidation}

## Required Controls

- Preserve fallback `{contract.fallback}`.
- Add the sampled shadow recomputation oracle before promotion.
- Implement every declared lifecycle hook and reader-retirement path.
- Run project tests, stateful differential sequences, high-churn, one-shot, memory-pressure, and end-to-end benchmarks.
- Pass local generated helpers through {lower}; report their Z3/Alive2 evidence separately.
- Do not claim generic source generation or lifecycle proof from Alive2.
"""
