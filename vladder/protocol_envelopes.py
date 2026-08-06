from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .language_adapter import canonical_hash
from .semantic_closure import EffectFootprint


PROTOCOL_ENVELOPE_SCHEMA = "protocol-envelopes-v1"


@dataclass(frozen=True)
class ProtocolEnvelope:
    id: str
    semantic_class: str
    applicability_guards: tuple[str, ...]
    effects: EffectFootprint
    transitions: tuple[tuple[str, str, str], ...]
    obligations: tuple[str, ...]
    crossing: str
    fallback: str

    def __post_init__(self) -> None:
        if not self.id or not self.semantic_class or not self.applicability_guards:
            raise ValueError("protocol envelope identity, class, and guards are required")
        if self.crossing not in {"permitted", "call-preserving-only", "forbidden"}:
            raise ValueError(f"unknown protocol crossing policy: {self.crossing}")
        if not self.fallback:
            raise ValueError("protocol envelope fallback is required")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "effects": self.effects.to_dict()}


def default_protocol_envelopes() -> tuple[ProtocolEnvelope, ...]:
    return (
        ProtocolEnvelope(
            "borrowed-contiguous-view", "borrowed_view",
            ("pointer and extent identify live contiguous storage", "declared aliases remain valid"),
            EffectFootprint(reads=("argmem",)),
            (("unpublished", "borrow", "live"), ("live", "return", "retired")),
            ("no read before borrow", "no read after owner lifetime", "bounds preserved"),
            "permitted", "retain the owning wrapper and call-preserving borrowed region",
        ),
        ProtocolEnvelope(
            "bounded-no-growth-append", "bounded_mutation",
            (
                "capacity minus size dominates every append",
                "element construction and destruction are trivial",
                "local operation cannot throw",
                "reallocation and allocator replacement are forbidden",
            ),
            EffectFootprint(reads=("argmem",), writes=("argmem",)),
            (("capacity_checked", "append", "extent_updated"),),
            ("every write is in capacity", "old elements are preserved", "new extent is exact"),
            "permitted", "use caller-owned span plus explicit output extent",
        ),
        ProtocolEnvelope(
            "aggregate-result", "result_projection",
            ("compiler ABI layout is captured", "every source field has one ordered channel"),
            EffectFootprint(),
            (("fields_live", "pack", "result_published"),),
            ("field order preserved", "padding is not observed as semantic data"),
            "permitted", "retain the native aggregate ABI",
        ),
        ProtocolEnvelope(
            "tagged-multi-exit", "control_result",
            ("finite ordinary exit set", "cleanup and unwind exits are modeled separately"),
            EffectFootprint(),
            (("executing", "ordinary_exit", "tagged_result"),),
            ("every ordinary exit maps to one tag", "live-outs match the selected exit"),
            "permitted", "retain the original CFG",
        ),
        ProtocolEnvelope(
            "trivial-cleanup", "cleanup",
            ("destroyed values have trivial destruction", "no cleanup has an external observer"),
            EffectFootprint(flags=("cleanup",)),
            (("live", "scope_exit", "retired"),),
            ("every lifetime ends once", "no use follows retirement"),
            "permitted", "retain source scope and cleanup points",
        ),
        ProtocolEnvelope(
            "scoped-allocation", "ownership",
            (
                "allocator identity is declared",
                "all success and failure exits are finite",
                "allocation and retirement pair under every exit",
            ),
            EffectFootprint(flags=("allocate", "deallocate", "cleanup")),
            (("empty", "allocate", "owned"), ("owned", "retire", "empty")),
            ("no leak", "no double retirement", "failure preserves baseline observables"),
            "call-preserving-only", "isolate a caller-owned bounded buffer",
        ),
        ProtocolEnvelope(
            "versioned-single-writer-publication", "publication",
            (
                "one writer owns candidate state",
                "readers select a complete published generation",
                "retirement waits for declared readers",
            ),
            EffectFootprint(flags=("publish", "invalidate", "synchronize")),
            (("current", "construct", "candidate"), ("candidate", "publish", "current")),
            ("no mixed generation", "invalidated generations are not reused", "fallback is atomic"),
            "call-preserving-only", "recompute and publish through the baseline protocol",
        ),
    )


def protocol_registry() -> dict[str, Any]:
    envelopes = default_protocol_envelopes()
    payload = {
        "schema_version": PROTOCOL_ENVELOPE_SCHEMA,
        "envelopes": [item.to_dict() for item in envelopes],
        "candidate_dimensions_added": 0,
    }
    return {**payload, "registry_hash": canonical_hash(payload)}


def validate_protocol_application(application: dict[str, Any]) -> dict[str, Any]:
    envelopes = {item.id: item for item in default_protocol_envelopes()}
    identifier = str(application.get("envelope", ""))
    if identifier not in envelopes:
        return {
            "envelope": identifier,
            "status": "unknown_envelope",
            "missing_guards": [],
            "obligations": [],
            "crossing": "forbidden",
        }
    envelope = envelopes[identifier]
    established = {str(item) for item in application.get("established_guards", [])}
    missing = [item for item in envelope.applicability_guards if item not in established]
    return {
        "envelope": identifier,
        "status": "closed" if not missing else "requires_guard_evidence",
        "missing_guards": missing,
        "obligations": list(envelope.obligations),
        "crossing": envelope.crossing if not missing else "forbidden",
        "fallback": envelope.fallback,
        "proof_method": application.get("proof_method", "required"),
        "proof_artifact": application.get("proof_artifact"),
    }


def match_protocol_envelope(native_constructs: Iterable[str]) -> tuple[str, ...]:
    text = " ".join(str(item) for item in native_constructs).lower()
    matches = []
    if any(token in text for token in ("span", "slice", "borrow", "data/size", "pointer_extent")):
        matches.append("borrowed-contiguous-view")
    if any(token in text for token in ("push_back", "emplace_back", "vec::push", "append")):
        matches.append("bounded-no-growth-append")
    if any(token in text for token in ("sret", "insertvalue", "aggregate", "struct return", "isbits")):
        matches.append("aggregate-result")
    if any(token in text for token in ("error union", "result<", "tagged exit", "multiple return")):
        matches.append("tagged-multi-exit")
    if any(token in text for token in ("drop", "defer", "finally", "trivial destructor")):
        matches.append("trivial-cleanup")
    if any(token in text for token in ("malloc", "allocate", "allocator", "gc allocation")):
        matches.append("scoped-allocation")
    if any(token in text for token in ("publish", "generation", "commit", "atomic swap")):
        matches.append("versioned-single-writer-publication")
    return tuple(sorted(set(matches)))
