from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_composition_native_corpus import audit
from vladder.composition_native import build_composition_trace
from vladder.lazy_search import FiniteParameterGrammar, LazySearchEngine


def _trace(project: str) -> dict:
    graph = {"nodes": [], "edges": [], "obligations": [], "effects": [], "protocols": [], "claims": []}
    result = LazySearchEngine().run(
        FiniteParameterGrammar("schedule", {"factor": (1, 2)}),
        {"semantic_hash": project * 8, "semantic_graph": graph}, mode="exhaustive",
    )
    rows = [{
        "state_id": state.identity, "candidate_id": str(index), "proof_status": "PASS",
        "physical_outcome": "distinct_realization" if index == 0 else "compiler_identical",
        "search_cost": {"evaluation_wall_ms": 1.0, "proof_calls": 1, "compiler_invocation_count": 1},
    } for index, state in enumerate(result.terminals)]
    return build_composition_trace(
        root={"root_id": project, "canonical_root_hash": project * 8, "semantic_graph": graph, "contracts": {}, "cross_tu_scope": {}},
        project_id=project, source_frontend="cpp", compiler_target="clang", hardware_context={},
        lazy_result=result, terminal_results=rows,
    )


def test_audit_distinguishes_incomplete_from_invalid_corpus(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"roots": [
        {"id": "duckdb", "project_id": "duckdb"},
        {"id": "rocksdb", "project_id": "rocksdb"},
    ]}))
    directory = tmp_path / "roots" / "duckdb"
    directory.mkdir(parents=True)
    (directory / "composition-native-search-trace.json").write_text(json.dumps(_trace("duckdb")))
    report = audit(tmp_path, manifest)
    assert report["status"] == "incomplete"
    assert report["summary"]["failure_count"] == 0
    assert report["summary"]["missing_root_count"] == 1
