from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .language_adapter import canonical_hash


EXECUTABLE_CLOSURE_SCHEMA = "vladder-executable-closure-v2"
EXECUTABLE_STAGES = (
    "recognition",
    "contract_inference",
    "applicability",
    "enumeration",
    "emission",
    "compilation",
    "proof",
    "physical_identity",
    "source_reconstruction",
)
STAGE_STATUSES = frozenset({"complete", "partial", "blocked", "unsupported", "not_attempted"})


@dataclass(frozen=True)
class ClosureStage:
    status: str
    authority: str
    detail: str
    artifact: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STAGE_STATUSES:
            raise ValueError(f"invalid executable closure status: {self.status}")
        if not self.authority or not self.detail:
            raise ValueError("closure stages require authority and detail")


@dataclass(frozen=True)
class ExecutableFamilyClosure:
    family: str
    grammar_version: str
    semantic_root_hash: str
    stages: Mapping[str, ClosureStage]
    parameter_domains: Mapping[str, tuple[Any, ...]]
    unresolved_contracts: tuple[str, ...] = ()
    external_boundaries: tuple[str, ...] = ()
    exhaustive_within_domain: bool = False
    closure_hash: str = ""

    def __post_init__(self) -> None:
        missing = set(EXECUTABLE_STAGES) - set(self.stages)
        extra = set(self.stages) - set(EXECUTABLE_STAGES)
        if missing or extra:
            raise ValueError(f"executable closure stage mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
        if any(not values for values in self.parameter_domains.values()):
            raise ValueError("parameter domains must be finite and nonempty")
        if self.exhaustive_within_domain:
            required = ("recognition", "contract_inference", "applicability", "enumeration")
            if any(self.stages[name].status != "complete" for name in required):
                raise ValueError("exhaustive closure requires complete recognition, contract, applicability, and enumeration")
        if not self.closure_hash:
            object.__setattr__(self, "closure_hash", canonical_hash(self._identity_payload()))

    @property
    def proof_unit_executable(self) -> bool:
        """Whether emitted proof units reached every executable evidence disposition.

        This does not imply that an owning source wrapper was reconstructed.  Keeping that
        distinction explicit prevents a generated helper from being reported as a production
        source replacement.
        """
        return all(
            self.stages[name].status == "complete"
            for name in (
                "recognition", "contract_inference", "applicability", "enumeration",
                "emission", "compilation", "proof", "physical_identity",
            )
        )

    @property
    def replacement_ready(self) -> bool:
        """Whether the proved realization is available as an owning source replacement."""
        return self.proof_unit_executable and self.stages["source_reconstruction"].status == "complete"

    @property
    def source_executable(self) -> bool:
        """Compatibility alias for pre-v2 consumers; scoped to an executable proof unit."""
        return self.proof_unit_executable

    @property
    def closure_scope(self) -> str:
        if self.replacement_ready:
            return "replacement_ready"
        if self.proof_unit_executable:
            return "proof_unit_only"
        return "non_executable"

    @property
    def first_incomplete_stage(self) -> str | None:
        return next((name for name in EXECUTABLE_STAGES if self.stages[name].status != "complete"), None)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTABLE_CLOSURE_SCHEMA,
            "family": self.family,
            "grammar_version": self.grammar_version,
            "semantic_root_hash": self.semantic_root_hash,
            "stages": {name: asdict(self.stages[name]) for name in EXECUTABLE_STAGES},
            "parameter_domains": {name: list(values) for name, values in sorted(self.parameter_domains.items())},
            "unresolved_contracts": list(self.unresolved_contracts),
            "external_boundaries": list(self.external_boundaries),
            "exhaustive_within_domain": self.exhaustive_within_domain,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "closure_hash": self.closure_hash,
            "proof_unit_executable": self.proof_unit_executable,
            "replacement_ready": self.replacement_ready,
            "closure_scope": self.closure_scope,
            # Retained for readers of the v1 report. It never implied owning-wrapper closure.
            "source_executable": self.source_executable,
            "source_executable_scope": "proof_unit",
            "first_incomplete_stage": self.first_incomplete_stage,
        }


def stage(status: str, authority: str, detail: str, artifact: str | None = None) -> ClosureStage:
    return ClosureStage(status, authority, detail, artifact)


def unattempted_stages(detail: str = "not reached") -> dict[str, ClosureStage]:
    return {name: stage("not_attempted", "none", detail) for name in EXECUTABLE_STAGES}


def closure_coverage(closures: list[ExecutableFamilyClosure]) -> dict[str, Any]:
    by_stage = {
        name: {
            status: sum(item.stages[name].status == status for item in closures)
            for status in sorted(STAGE_STATUSES)
        }
        for name in EXECUTABLE_STAGES
    }
    return {
        "schema_version": "vladder-executable-closure-coverage-v2",
        "family_count": len(closures),
        "proof_unit_executable_count": sum(item.proof_unit_executable for item in closures),
        "replacement_ready_count": sum(item.replacement_ready for item in closures),
        "source_executable_count": sum(item.source_executable for item in closures),
        "exhaustive_count": sum(item.exhaustive_within_domain for item in closures),
        "stage_counts": by_stage,
        "first_incomplete_stage_counts": {
            name: sum(
                (item.first_incomplete_stage or "complete") == name
                for item in closures
            )
            for name in (*EXECUTABLE_STAGES, "complete")
        },
    }
