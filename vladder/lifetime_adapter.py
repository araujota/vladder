from __future__ import annotations

from .language_adapter import (
    ProtocolTransition,
    SemanticClaim,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    obligation,
)
from .lifetime_graph import LifetimeFlowGraph


def lifetime_semantic_flow_graph(graph: LifetimeFlowGraph) -> SemanticFlowGraph:
    """Project LifetimeFlowGraph into the shared SemanticFlowGraph v2 vocabulary."""
    nodes: list[SemanticFlowNode] = []
    edges: list[SemanticFlowEdge] = []
    obligations = []
    effects: list[SemanticEffect] = []
    protocols: list[ProtocolTransition] = []

    def node(identifier: str, kind: str, operation: str, inputs: tuple[str, ...], output: str, attributes: dict) -> None:
        nodes.append(SemanticFlowNode(
            identifier,
            kind,
            operation,
            inputs,
            output,
            attributes,
            {"adapter": "lifetime-semantic-flow-v1", "domain": graph.domain},
            (),
        ))
        for ordinal, source in enumerate(inputs):
            edges.append(SemanticFlowEdge(
                f"{source}->{identifier}:{ordinal}",
                source,
                identifier,
                output,
                "shared" if kind in {"View", "StateRead"} else "owned",
                str(attributes.get("alias_set", "lifetime")),
                str(attributes.get("scope", "semantic")),
                "version-before-use",
                realization=str(attributes.get("placement", "semantic")),
                memory_region=str(attributes.get("placement", "unspecified")),
                validity_scope=str(attributes.get("scope", "semantic")),
            ))

    for item in graph.information:
        prefix = f"information.{item.id}"
        source_id = f"{prefix}.source"
        realization_id = f"{prefix}.realization"
        node(source_id, "StateRead", "authoritative-information", (), item.representation, {
            "semantic_source": list(item.source),
            "owner": item.owner,
            "scope": item.current.scope,
            "alias_set": item.alias_set,
        })
        node(realization_id, "Materialize", item.realization_kind, (source_id,), item.representation, {
            "scope": item.current.scope,
            "placement": item.current.placement,
            "construction": item.current.construction,
            "consistency": item.current.consistency,
            "byte_size": item.byte_size,
            "candidate_scopes": list(item.candidate_scopes),
            "candidate_placements": list(item.candidate_placements),
            "traits": list(item.traits),
            "alias_set": item.alias_set,
        })
        obligation_id = f"lifetime.{item.id}.validity"
        obligations.append(obligation(
            obligation_id,
            "lifetime",
            "realization is published before use, refreshed at every invalidator, and retired after its final reader",
            scope=item.current.scope,
            proof_method="bounded-state-transition-and-differential-replay",
            facts={"invalidators": list(item.invalidators), "fallback": item.fallback},
        ))
        for index, consumer in enumerate(item.consumers):
            consumer_id = f"{prefix}.consumer.{index}"
            node(consumer_id, "View", "consume-valid-realization", (realization_id,), item.representation, {
                "consumer": consumer.id,
                "scope": consumer.scope,
                "independent_observer": consumer.independent_observer,
                "placement": item.current.placement,
                "alias_set": item.alias_set,
            })
        effects.extend([
            SemanticEffect(
                f"{prefix}.publish",
                "Publish",
                "construction",
                item.current.placement,
                "versioned-realization",
                item.current.publication,
                (realization_id,),
                (obligation_id,),
                {"information_id": item.id},
            ),
            SemanticEffect(
                f"{prefix}.invalidate",
                "Invalidate",
                "mutation",
                item.current.placement,
                "validity-frontier",
                "before-next-read",
                (realization_id,),
                (obligation_id,),
                {"invalidators": list(item.invalidators)},
            ),
        ])
        protocols.extend([
            ProtocolTransition(
                f"{prefix}.reuse",
                "Lifetime",
                "published",
                "non-invalidating-consumption",
                "published",
                "source version unchanged",
                (obligation_id,),
            ),
            ProtocolTransition(
                f"{prefix}.refresh",
                "Invalidation",
                "published",
                "declared invalidator",
                "invalid",
                "source version changed",
                (obligation_id,),
            ),
        ])
    claims = (
        SemanticClaim(
            "lifetime.plan.scope",
            "required",
            "candidate plans preserve derivation, publication, invalidation, consumption, and retirement observables",
            "lifetime-flow-graph",
        ),
    )
    return SemanticFlowGraph(
        graph.name,
        "language-neutral",
        "repository-and-runtime-trace",
        "lifetime-flow-v1",
        graph.name,
        tuple(nodes),
        tuple(edges),
        {"domain": graph.domain, "manifest_hash": graph.manifest_hash, **graph.contract},
        ("owning source reconstruction", "unbounded external protocol behavior"),
        obligations=tuple(obligations),
        effects=tuple(effects),
        protocols=tuple(protocols),
        claims=claims,
    )
