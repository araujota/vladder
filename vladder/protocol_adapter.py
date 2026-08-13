from __future__ import annotations

from typing import Any, Mapping

from .language_adapter import (
    ProtocolTransition,
    SemanticClaim,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    obligation,
)


def protocol_semantic_flow_graph(raw: Mapping[str, Any], identity: str) -> SemanticFlowGraph:
    """Project a bounded state/device protocol into the universal semantic vocabulary."""
    protocol = str(raw.get("protocol") or raw.get("kind") or "external")
    protocol_type = {
        "queue": "Queue",
        "dma": "DMA",
        "presentation": "Presentation",
        "versioned_cache": "Invalidation",
        "transactional_publication": "Publication",
        "finite_resource": "Ownership",
    }.get(protocol, "Concurrency")
    transitions = tuple(item for item in raw.get("transitions", ()) if isinstance(item, Mapping))
    nodes = [
        SemanticFlowNode(
            "authority",
            "StateRead",
            "authoritative-protocol-state",
            (),
            "authoritative-state",
            {"protocol": protocol},
            {"adapter": "bounded-protocol-semantic-flow-v1"},
            (),
        )
    ]
    edges: list[SemanticFlowEdge] = []
    typed_transitions: list[ProtocolTransition] = []
    for index, transition in enumerate(transitions):
        identifier = str(transition.get("id") or f"transition-{index}")
        node_id = f"transition.{identifier}"
        nodes.append(SemanticFlowNode(
            node_id,
            "StateWrite",
            "bounded-protocol-transition",
            ("authority",),
            "state-transition",
            dict(transition),
            {"adapter": "bounded-protocol-semantic-flow-v1"},
            (),
        ))
        edges.append(SemanticFlowEdge(
            f"authority->{node_id}",
            "authority",
            node_id,
            "state-version",
            "transition-preserving",
            "protocol-state",
            "state",
            "happens-before",
            realization="declared-transition",
            validity_scope="protocol-instance",
        ))
        typed_transitions.append(ProtocolTransition(
            identifier,
            protocol_type,
            str(transition.get("from", "declared")),
            str(transition.get("event", identifier)),
            str(transition.get("to", "declared")),
            " && ".join(str(item) for item in transition.get("guards", ())) or "true",
            ("protocol.transition.system",),
            {"external_boundary": bool(transition.get("external_boundary"))},
        ))
    return SemanticFlowGraph(
        identity,
        "language-neutral",
        "bounded-protocol-manifest",
        "bounded-protocol-v1",
        protocol,
        tuple(nodes),
        tuple(edges),
        {"protocol": protocol},
        ("external implementation internals", "physical timing"),
        obligations=(
            obligation(
                "protocol.transition.system",
                "state",
                "declared transitions preserve state domains, ordering, publication, rollback, and retirement obligations",
                scope="bounded-protocol",
                proof_method="Z3 bounded state/event verification",
            ),
        ),
        protocols=tuple(typed_transitions),
        claims=(SemanticClaim(
            "protocol.boundary",
            "required",
            "proof covers the declared finite protocol, not driver, network, or owning source implementation internals",
            "bounded-protocol",
        ),),
    )


def protocol_projection_domains(raw: Mapping[str, Any]) -> tuple[str, ...]:
    dimensions = {"state-domain", "ordering"}
    text = str(dict(raw)).lower()
    if "publish" in text or "commit" in text:
        dimensions.add("publication")
    if "rollback" in text or "failure" in text or "cancel" in text:
        dimensions.add("rollback")
    if "retire" in text or "release" in text or "reader" in text:
        dimensions.add("retirement")
    if "external" in text or raw.get("kind") in {"queue", "dma", "presentation"}:
        dimensions.add("external-boundary")
    return tuple(sorted(dimensions))
