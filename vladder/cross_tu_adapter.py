from __future__ import annotations

from .language_adapter import (
    SemanticClaim,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    obligation,
)


def cross_tu_semantic_flow_graph(report: dict) -> SemanticFlowGraph:
    slice_graph = report["slice"]
    nodes: list[SemanticFlowNode] = []
    edges: list[SemanticFlowEdge] = []
    obligations = []
    function_ids = {str(item["id"]) for item in slice_graph.get("functions", [])}
    for item in slice_graph.get("functions", []):
        identifier = str(item["id"])
        contracts = dict(item.get("contracts", {}))
        nodes.append(SemanticFlowNode(
            identifier,
            "Call",
            "definition-visible-function-summary",
            (),
            "function-summary",
            {
                "local_effects": item.get("local_effects", {}),
                "transitive_effects": item.get("transitive_effects", {}),
                "contracts": contracts,
            },
            {
                "adapter": "cross-tu-semantic-flow-v1",
                "source_sha256": contracts.get("source_sha256"),
                "command_sha256": contracts.get("command_sha256"),
            },
            (),
        ))
    for index, boundary in enumerate(slice_graph.get("boundaries", [])):
        identifier = f"boundary.{index}"
        nodes.append(SemanticFlowNode(
            identifier,
            "Call",
            "explicit-external-or-ambiguous-boundary",
            (),
            "protocol-boundary",
            dict(boundary),
            {"adapter": "cross-tu-semantic-flow-v1"},
            (),
        ))
        caller = str(boundary.get("caller", ""))
        if caller in function_ids:
            edges.append(SemanticFlowEdge(
                f"{caller}->{identifier}", caller, identifier, "call-effect",
                "call-preserving", "external", "call", "program-order",
                realization="protocol-boundary", validity_scope="call",
            ))
    for index, edge in enumerate(slice_graph.get("edges", [])):
        source = str(edge["source"])
        destination = str(edge["destination"])
        if source not in function_ids or destination not in function_ids:
            continue
        edges.append(SemanticFlowEdge(
            f"call.{index}", source, destination, "call-relation",
            "call-preserving", "cross-tu", "call", "program-order",
            realization="definition-visible", validity_scope="selected-build",
        ))
    for index, item in enumerate(report.get("selected_build", {}).get("functions", ())):
        if item.get("status") != "applicable" or item.get("function_id") not in function_ids:
            continue
        identifier = f"selected-region.{index}"
        nodes.append(SemanticFlowNode(
            identifier,
            "Loop",
            "bounded-selected-build-region",
            (str(item["function_id"]),),
            "region-state",
            {"count": int(item.get("region_count", 0)), "exactness": "exact"},
            {"adapter": "cross-tu-selected-build-v1"},
            (),
        ))
        edges.append(SemanticFlowEdge(
            f"region.{index}", str(item["function_id"]), identifier, "region-state",
            "ephemeral", "cross-tu", "function", "program-order",
            realization="selected-build-region", validity_scope="selected-build",
        ))
    obligations.append(obligation(
        "cross-tu.definition.identity",
        "validation",
        "every composed call edge resolves to one selected-build definition and immutable compiler/source identity",
        scope="selected-build-slice",
        proof_method="whole-build-index-plus-Z3-summary-composition",
    ))
    obligations.append(obligation(
        "cross-tu.functional.boundary",
        "external-effect",
        "call-preserving summaries do not authorize cross-call functional rewrites without a functional helper contract",
        scope="selected-build-slice",
        proof_method="explicit-boundary-exclusion",
    ))
    return SemanticFlowGraph(
        "cross-tu-slice",
        "cpp",
        "selected-build-compile-commands",
        "cross-tu-summary-v1",
        ",".join(str(item) for item in slice_graph.get("seeds", [])),
        tuple(nodes),
        tuple(edges),
        {
            "budgets": slice_graph.get("budgets", {}),
            "ownership": report.get("ownership", {}).get("closure"),
            "truncated": bool(slice_graph.get("truncated")),
        },
        (
            "functional equivalence across call boundaries",
            "external protocol implementation semantics",
        ),
        obligations=tuple(obligations),
        claims=(SemanticClaim(
            "cross-tu.closure.scope",
            "required",
            "composition preserves definition identity, effects, ownership disposition, and explicit boundaries",
            "selected-build-slice",
        ),),
    )
