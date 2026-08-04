from __future__ import annotations

from typing import Any, Mapping

from .lowering import (
    LoweringMode,
    LoweringOperation,
    LoweringPlan,
    LoweringRequest,
    LoweringResult,
    LoweringStatus,
    canonical_plan_id,
)


FACT_OVERRIDES: dict[str, tuple[str, ...]] = {
    "bounded-reassociate": ("floating-point policy", "determinism"),
    "dispatch-reorder": ("branch distribution", "side-effect freedom"),
    "interchange": ("iteration independence", "dependence distance"),
    "fuse": ("iteration independence", "observable ordering"),
    "fission": ("dependence distance", "observable ordering"),
    "add-restrict": ("pointer provenance", "alias sets", "object bounds"),
    "alignment-assume": ("alignment", "object bounds"),
    "load-hoist": ("alias sets", "lifetime", "volatile policy"),
    "store-sink": ("alias sets", "lifetime", "volatile policy"),
    "pairwise-tree": ("associativity", "floating-point tolerance", "determinism"),
    "online-max-sum": ("floating-point tolerance", "determinism"),
    "aos-to-soa": ("layout ownership", "consumer coverage", "ABI boundary"),
    "pack-fields": ("layout ownership", "padding interpretation", "serialization"),
    "layout-adapter": ("ABI boundary", "consumer coverage"),
    "producer-consumer-fuse": ("no intermediate observers", "alias legality", "side effects"),
    "scratch-reuse": ("lifetime", "alias legality"),
    "ring-window": ("state ownership", "capacity", "event ordering", "initial state"),
    "incremental-update": ("transition invariants", "event ordering", "initial state"),
    "spsc-index-layout": ("thread topology", "happens-before", "object lifetime"),
    "release-acquire-pair": ("thread topology", "happens-before", "atomic width"),
    "tentative-commit": ("thread topology", "happens-before", "progress requirement"),
    "isa-guard": ("guard completeness", "fallback semantics", "deployment preconditions"),
    "portfolio-plan": ("guard completeness", "fallback semantics", "input distribution"),
    "avx2": ("target ISA", "OS vector state", "fallback availability"),
    "avx512": ("target ISA", "OS vector state", "fallback availability"),
    "operator-compose": ("graph ownership", "shape compatibility", "state boundaries"),
    "weight-major-traversal": ("shape compatibility", "latency constraints", "workload portfolio"),
    "runtime-dispatch-plan": ("latency constraints", "workload portfolio", "state boundaries"),
    "repeated-derivation-elimination": ("semantic source authority", "scope containment", "complete mutation classification", "fallback equivalence"),
    "serialization-body-reuse": ("semantic source authority", "scope containment", "complete mutation classification", "fallback equivalence"),
    "immutable-mutable-projection-split": ("semantic source authority", "complete mutation classification", "ownership and consistency", "fallback equivalence"),
    "intermediate-realization-elimination": ("semantic source authority", "scope containment", "publication and retirement", "fallback equivalence"),
    "placement-resident-state": ("semantic source authority", "complete mutation classification", "ownership and consistency", "publication and retirement", "fallback equivalence"),
}


PARAMETER_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "unroll": ("factor",),
    "tile": ("tile_size",),
    "interchange": ("permutation",),
    "peel-tail": ("peel_count",),
    "pipeline-blocks": ("depth",),
    "prefetch": ("distance",),
    "block-reduce": ("block_size",),
    "hierarchical-scan": ("block_size",),
    "block-layout": ("block_shape",),
    "pad-alignment": ("alignment",),
    "ring-window": ("capacity",),
    "fixed-dimension": ("dimension", "value"),
    "trip-count-bucket": ("minimum", "maximum"),
    "alignment-guard": ("alignment",),
    "common-case-guard": ("predicate",),
    "unroll-factor": ("factor",),
    "prefetch-distance": ("distance",),
    "compiler-variant": ("flags",),
    "pipeline-tile": ("tile_size",),
    "token-tile": ("token_count",),
    "sequence-tile": ("sequence_count",),
}


class DeclarativeFamilyLowerer:
    family_id = ""
    region_kind = "region"
    rules: Mapping[str, str] = {}

    def covered_rules(self, family: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(self.rules)

    def required_facts(self, family: Mapping[str, Any], rule: str) -> tuple[str, ...]:
        return FACT_OVERRIDES.get(rule, tuple(str(item) for item in family["contract_facts"]))

    def lower(self, registry, family, request: LoweringRequest) -> LoweringResult:
        input_identity = request.resolved_input_identity()
        facts = self.required_facts(family, request.rule)
        parameters = PARAMETER_REQUIREMENTS.get(request.rule, ())
        missing_facts = tuple(fact for fact in facts if not request.contract_facts.get(fact))
        missing_parameters = tuple(name for name in parameters if name not in request.parameters)
        if missing_facts or missing_parameters:
            diagnostics = tuple(f"missing contract fact: {item}" for item in missing_facts) + tuple(
                f"missing parameter: {item}" for item in missing_parameters
            )
            return LoweringResult(LoweringStatus.REJECTED, None, diagnostics)

        effect = self.rules[request.rule]
        route = dict(family.get("source_routes", {})).get(request.rule)
        emission = "specialized" if route else "plan"
        operations = (
            LoweringOperation(
                "contract.guard",
                (input_identity,),
                (f"guarded:{input_identity}",),
                {"facts": list(facts)},
            ),
            LoweringOperation(
                f"{self.family_id}.{request.rule}",
                (f"guarded:{input_identity}",),
                (f"lowered:{input_identity}",),
                {"region_kind": self.region_kind, "effect": effect, "parameters": dict(request.parameters)},
            ),
            LoweringOperation(
                "proof.attach",
                (f"lowered:{input_identity}",),
                (f"verified:{input_identity}",),
                {"strategies": list(family["proof_strategies"])},
            ),
            LoweringOperation(
                "cost.observe",
                (f"verified:{input_identity}",),
                (f"candidate:{input_identity}",),
                {"signals": list(family["cost_signals"])},
            ),
        )
        payload = {
            "grammar": registry.sha256,
            "family": self.family_id,
            "rule": request.rule,
            "facts": dict(sorted(request.contract_facts.items())),
            "parameters": dict(sorted(request.parameters.items())),
            "input": input_identity,
            "operations": [item.to_dict() for item in operations],
            "backend": route,
        }
        plan = LoweringPlan(
            canonical_plan_id(payload),
            registry.version,
            registry.sha256,
            self.family_id,
            request.rule,
            str(family["status"]),
            facts,
            parameters,
            operations,
            tuple(str(item) for item in family["proof_strategies"]),
            tuple(str(item) for item in family["cost_signals"]),
            str(route) if route else None,
            emission,
            input_identity,
        )
        if request.mode is LoweringMode.SOURCE:
            if not route:
                return LoweringResult(
                    LoweringStatus.UNSUPPORTED,
                    plan,
                    (f"{self.family_id}/{request.rule} has plan lowering but no source backend",),
                )
            return LoweringResult(
                LoweringStatus.ROUTED,
                plan,
                ("source generation requires the specialized backend and its shape-specific input",),
            )
        return LoweringResult(LoweringStatus.PLANNED, plan)


class ExpressionAlgebraLowerer(DeclarativeFamilyLowerer):
    family_id = "expression-algebra"
    region_kind = "expression-dag"
    rules = {
        "constant-fold": "evaluate a typed constant subgraph and replace it with its canonical literal",
        "identity-elimination": "remove an algebraic identity while preserving poison and floating-point policy",
        "strength-reduce": "replace an expensive operation with a contract-equivalent cheaper expression",
        "select-normalize": "canonicalize equivalent conditional expressions into a select DAG",
        "bitvector-canonicalize": "normalize fixed-width boolean and bit-vector operations",
        "bounded-reassociate": "reassociate a bounded expression only under its numerical contract",
    }


class ControlFlowLowerer(DeclarativeFamilyLowerer):
    family_id = "control-flow"
    region_kind = "control-flow-region"
    rules = {
        "branch-to-select": "replace a side-effect-free branch diamond with predicated selection",
        "select-to-mask": "materialize a predicate as a typed mask and combine guarded values",
        "predicate-aggregate": "combine independent predicates into one decision value",
        "rare-path-isolate": "split an uncommon path behind a guarded cold boundary",
        "guard-hoist": "move a loop-invariant or region-invariant guard to its dominating boundary",
        "dispatch-reorder": "order semantically independent dispatch tests by declared distribution",
    }


class LoopScheduleLowerer(DeclarativeFamilyLowerer):
    family_id = "loop-schedule"
    region_kind = "loop-nest"
    rules = {
        "unroll": "replicate a dependence-safe loop body by the requested factor",
        "tile": "partition an iteration space into bounded cache-sized tiles",
        "interchange": "permute independent loop dimensions",
        "fuse": "merge iteration-compatible loops while preserving dependence order",
        "fission": "split a loop at a legal dependence boundary",
        "peel-tail": "separate a bounded prefix or suffix for aligned steady-state execution",
        "pipeline-blocks": "overlap independent load, transform, and consume stages across blocks",
    }


class MemoryAliasLowerer(DeclarativeFamilyLowerer):
    family_id = "memory-alias"
    region_kind = "memory-region"
    rules = {
        "prove-nonalias": "derive disjoint pointer footprints from bounds and provenance facts",
        "add-restrict": "attach a nonalias source contract after footprint proof",
        "alignment-assume": "introduce a checked or deployment-level alignment precondition",
        "load-hoist": "move an invariant nonvolatile load above a region with no aliasing store",
        "store-sink": "delay a store across a region with no observable intervening access",
        "prefetch": "issue a nonsemantic prefetch at a bounded future address",
        "address-strength-reduce": "replace repeated address arithmetic with an induction expression",
    }


class ReductionScanLowerer(DeclarativeFamilyLowerer):
    family_id = "reductions-scans"
    region_kind = "reduction-or-recurrence"
    rules = {
        "multi-accumulator": "partition an associative reduction into independent accumulator chains",
        "pairwise-tree": "combine reduction values through a balanced pairwise topology",
        "block-reduce": "reduce bounded blocks and combine their partial values",
        "hierarchical-scan": "scan local blocks, scan block totals, and apply block prefixes",
        "online-max-sum": "maintain a numerically contracted online maximum and normalized sum",
        "incremental-state": "replace recomputation with an equivalent bounded recurrence update",
    }


class LayoutRepresentationLowerer(DeclarativeFamilyLowerer):
    family_id = "layout-representation"
    region_kind = "layout-region"
    rules = {
        "aos-to-soa": "transpose owned records into independently traversable field streams",
        "interleave-pairs": "place corresponding blocks from sibling streams adjacently",
        "split-planes": "separate interleaved logical components into independent planes",
        "block-layout": "map a logical tensor into fixed multidimensional physical blocks",
        "pad-alignment": "insert non-data padding to establish an alignment invariant",
        "pack-fields": "encode declared fixed-width fields into a packed representation",
        "layout-adapter": "insert a verified boundary conversion between logical and physical layouts",
    }


class MaterializationFusionLowerer(DeclarativeFamilyLowerer):
    family_id = "materialization-fusion"
    region_kind = "producer-consumer-region"
    rules = {
        "loop-fuse": "execute compatible producer and consumer iterations in one loop",
        "producer-consumer-fuse": "forward produced values directly into their sole consumer",
        "epilogue-fuse": "apply a terminal transform before the producer result is materialized",
        "tile-materialize": "materialize only a bounded tile instead of the complete intermediate",
        "scratch-reuse": "assign nonoverlapping lifetimes to the same scratch region",
        "recompute-cheap-value": "replace a temporary read with contract-equivalent local recomputation",
    }


class StateWindowLowerer(DeclarativeFamilyLowerer):
    family_id = "state-window"
    region_kind = "bounded-transition-system"
    rules = {
        "ring-window": "map a fixed logical window onto modulo-indexed bounded storage",
        "incremental-update": "update derived state from one admitted transition",
        "state-cache": "retain derived state with an explicit invalidation transition",
        "derived-state": "replace stored state with a deterministic derivation from canonical state",
        "eager-lazy-maintenance": "move state maintenance between updates and checked reads",
        "change-mask-output": "emit a bounded changed-field mask instead of unchanged full state",
    }


class ConcurrencyMemoryOrderLowerer(DeclarativeFamilyLowerer):
    family_id = "concurrency-memory-order"
    region_kind = "concurrent-region"
    rules = {
        "spsc-index-layout": "separate producer and consumer indices under one-producer one-consumer ownership",
        "release-acquire-pair": "publish initialized state with release and consume it after acquire",
        "producer-batch": "reserve and publish multiple producer slots in one bounded batch",
        "consumer-batch": "acquire and retire multiple available consumer slots in one bounded batch",
        "tentative-commit": "stage speculative state and publish only the verified committed prefix",
    }


class SpecializationDispatchLowerer(DeclarativeFamilyLowerer):
    family_id = "specialization-dispatch"
    region_kind = "dispatch-region"
    rules = {
        "fixed-dimension": "specialize a region for one checked or contracted dimension",
        "trip-count-bucket": "dispatch bounded trip-count intervals to separate realizations",
        "isa-guard": "select an ISA-specific realization behind a complete target guard",
        "alignment-guard": "select an aligned realization with an unaligned fallback",
        "common-case-guard": "isolate a declared common input case behind a semantic guard",
        "portfolio-plan": "select realizations by a constrained weighted workload objective",
    }


class HardwareCodegenLowerer(DeclarativeFamilyLowerer):
    family_id = "hardware-codegen"
    region_kind = "target-code-region"
    rules = {
        "scalar": "request the scalar target realization",
        "sse": "request an SSE-width realization with target guard",
        "avx2": "request an AVX2-width realization with target guard",
        "avx512": "request an AVX-512-width realization with target guard",
        "unroll-factor": "request target lowering with a bounded unroll factor",
        "prefetch-distance": "request target lowering with a bounded software prefetch distance",
        "compiler-variant": "compile an otherwise identical graph with an audited flag set",
    }


class OperatorPipelineLowerer(DeclarativeFamilyLowerer):
    family_id = "operator-pipeline"
    region_kind = "hierarchical-flow-graph"
    rules = {
        "operator-compose": "compose shape-compatible operators across an unobserved boundary",
        "pipeline-tile": "traverse a pipeline in bounded producer-consumer tiles",
        "weight-major-traversal": "reuse each loaded weight block across admitted activation lanes",
        "token-tile": "execute a bounded group of token lanes through one traversal",
        "sequence-tile": "execute bounded lanes from independent sequences through one traversal",
        "runtime-dispatch-plan": "select a verified execution graph from declared runtime conditions",
    }


class LifetimeRealizationLowerer(DeclarativeFamilyLowerer):
    family_id = "lifetime-realization"
    region_kind = "semantic-lifetime-region"
    rules = {
        "repeated-derivation-elimination": "construct derived information once per valid semantic scope and reuse until an explicit invalidator",
        "serialization-body-reuse": "separate an invariant serialized body from per-emission envelope state",
        "immutable-mutable-projection-split": "retain the stable projection while updating only mutation-dependent state",
        "intermediate-realization-elimination": "forward directly to a consumer or retire storage at the final-use frontier",
        "placement-resident-state": "retain a versioned realization at the consuming hardware or ownership boundary",
    }
