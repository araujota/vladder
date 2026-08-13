from __future__ import annotations

import json
from pathlib import Path
import subprocess

from vladder.whole_build import (
    BidirectionalProgramSlice,
    CrossTUSummaryDatabase,
    OwnershipClosureGraph,
    SummaryCompositionProof,
    WholeBuildIndex,
    run_cross_tu_closure,
)
from vladder.executable_search import ExecutableSearchEngine, ExecutableSearchRequest
from vladder.training_workflow import create_training_bundle_from_search_trace
from vladder.toolchain import discover_toolchain


def _fixture(tmp_path: Path) -> Path:
    compiler = discover_toolchain().compiler
    sources = {
        "helper.cpp": 'extern "C" int external_authority(int);\nextern "C" int helper(int x) { return external_authority(x) + 3; }\n',
        "root.cpp": 'extern "C" int helper(int);\nextern "C" int root(int x) { return helper(x) + 1; }\n',
        "caller.cpp": 'extern "C" int root(int);\nextern "C" int caller(int x) { return root(x) * 2; }\n',
        "callback.cpp": 'extern "C" int invoke_cb(int (*cb)(int), int x) { return cb(x); }\n',
        "owner.cpp": '#include <cstdlib>\nvolatile void *owner_sink;\nextern "C" int own() { void *p = std::malloc(4); owner_sink = p; if (!p) return 0; std::free(p); return 1; }\n',
        "loop_helper.cpp": 'extern "C" void loop_helper(float *dst, const float *src, unsigned n) { for (unsigned i = 0; i < n; ++i) { dst[i] = src[i] * 2.0f; } }\n',
        "loop_root.cpp": 'extern "C" void loop_helper(float *, const float *, unsigned);\nextern "C" void loop_root(float *dst, const float *src, unsigned n) { loop_helper(dst, src, n); for (unsigned i = 0; i < n; ++i) { dst[i] += 1.0f; } }\n',
    }
    entries = []
    for name, source in sources.items():
        path = tmp_path / name
        path.write_text(source)
        output = tmp_path / f"{name}.o"
        arguments = [compiler, "-std=c++20", "-O2", "-c", str(path), "-o", str(output)]
        subprocess.run(arguments, check=True, capture_output=True, text=True)
        entries.append({
            "directory": str(tmp_path),
            "file": str(path),
            "output": str(output),
            "arguments": arguments,
        })
    database = tmp_path / "compile_commands.json"
    database.write_text(json.dumps(entries, indent=2))
    return database


def test_whole_build_index_resolves_project_helpers(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    index = WholeBuildIndex.from_compilation_database(database)
    assert index.resolve_definition("root")["status"] == "unique"
    assert index.resolve_definition("helper")["status"] == "unique"
    assert index.resolve_definition("external_authority")["status"] == "unresolved"
    assert len(index.references["helper"]) == 1
    persisted = index.write(tmp_path / "index.json")
    loaded = WholeBuildIndex.read(persisted)
    assert loaded.to_dict()["index_sha256"] == index.to_dict()["index_sha256"]


def test_cross_tu_summary_slice_and_proof(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    index = WholeBuildIndex.from_compilation_database(database)
    summaries = CrossTUSummaryDatabase(index, tmp_path / "summary-db")
    root = summaries.summary("root")
    assert root is not None
    root_helper = [relation for relation in root.calls if relation.callsite == "helper"]
    assert len(root_helper) == 1
    assert root_helper[0].kind == "definition"
    graph = BidirectionalProgramSlice(index, summaries, max_upstream=1, max_downstream=2).build(["root"])
    identities = {item["id"] for item in graph["functions"]}
    assert {"cpp::caller", "cpp::root", "cpp::helper"} <= identities
    assert any(item.get("symbol") == "external_authority" for item in graph["boundaries"])
    ownership = OwnershipClosureGraph().build(graph)
    proof = SummaryCompositionProof(index).prove(graph, ownership, tmp_path / "proof")
    assert proof["status"] == "PASS"
    assert all(item["status"] == "PASS" for item in proof["obligations"])


def test_cross_tu_workflow_is_analysis_only(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.glob("*.cpp")}
    report = run_cross_tu_closure(database, ["root"], tmp_path / "out", max_upstream=1, max_downstream=2)
    assert report["status"] == "pass"
    assert report["source_changes_performed"] is False
    assert report["candidate_dimensions_added"] == 0
    assert before == {path.name: path.read_bytes() for path in tmp_path.glob("*.cpp")}
    assert (tmp_path / "out" / "cross-tu-closure-report.json").exists()


def test_indirect_calls_and_ownership_are_explicit(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    index = WholeBuildIndex.from_compilation_database(database)
    summaries = CrossTUSummaryDatabase(index, tmp_path / "semantic-db")
    callback = BidirectionalProgramSlice(index, summaries, max_upstream=0, max_downstream=1).build(["invoke_cb"])
    assert any(item.get("status") == "opaque" for item in callback["boundaries"])
    owner = BidirectionalProgramSlice(index, summaries, max_upstream=0, max_downstream=0).build(["own"])
    ownership = OwnershipClosureGraph().build(owner)
    edge_kinds = {item["kind"] for item in ownership["edges"]}
    assert {"construct", "retire"} <= edge_kinds


def test_ambiguous_weak_definitions_fail_closed(tmp_path: Path) -> None:
    compiler = discover_toolchain().compiler
    entries = []
    for name in ("weak_a.cpp", "weak_b.cpp"):
        path = tmp_path / name
        path.write_text('extern "C" __attribute__((weak)) int shared_weak() { return 7; }\n')
        output = tmp_path / f"{name}.o"
        arguments = [compiler, "-c", str(path), "-o", str(output)]
        subprocess.run(arguments, check=True, capture_output=True, text=True)
        entries.append({"directory": str(tmp_path), "file": str(path), "output": str(output), "arguments": arguments})
    database = tmp_path / "compile_commands.json"
    database.write_text(json.dumps(entries))
    index = WholeBuildIndex.from_compilation_database(database)
    assert index.resolve_definition("shared_weak")["status"] == "ambiguous_odr"
    summaries = CrossTUSummaryDatabase(index, tmp_path / "ambiguous-db")
    assert summaries.summary("shared_weak") is None


def test_cross_tu_compositions_are_lazy_memoized_and_boundary_explicit(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    result = ExecutableSearchEngine(tmp_path / "cache").search(ExecutableSearchRequest(
        "cross-tu-root",
        tmp_path / "out",
        family="cross-tu-composition",
        language="cpp",
        project_id="fixture",
        compile_commands=database,
        cross_tu_seeds=("root",),
        max_upstream=1,
        max_downstream=2,
    ))
    assert result["status"] == "pass"
    assert result["closure"]["exhaustive_within_domain"] is True
    assert result["closure"]["source_executable"] is False
    assert result["closure"]["stages"]["proof"]["status"] == "complete"
    assert len(result["terminals"]) == 1
    assert result["terminals"][0]["proof_status"] == "PASS"
    nodes = result["lazy_search"]["nodes"]
    assert any(item["action"].get("op") == "add_definition_edge" for item in nodes)
    assert any(item["action"].get("op") == "preserve_protocol_boundary" for item in nodes)
    assert result["lazy_search"]["canonicalized"] > 0
    bundle = create_training_bundle_from_search_trace(
        result["trace"],
        tmp_path / "cross-tu-training.json",
        project_id="fixture",
        producer_agent="test",
        producer_model="test",
        identity_path=tmp_path / "identity.json",
    )
    labels = {
        item["survival"]["class"]
        for item in bundle["branches"]
        if not item["baseline"]
    }
    assert labels <= {
        "KEEP_UNCERTAIN", "PRUNE_HIGH_CONFIDENCE", "BLOCKED_BY_CONTRACT",
    }
    assert "KEEP_UNCERTAIN" in labels


def test_cross_tu_search_regenerates_and_proves_selected_build_regions(tmp_path: Path) -> None:
    database = _fixture(tmp_path)
    result = ExecutableSearchEngine(tmp_path / "cache").search(ExecutableSearchRequest(
        "cross-tu-loop",
        tmp_path / "loop-out",
        family="cross-tu-composition",
        language="cpp",
        project_id="fixture",
        compile_commands=database,
        cross_tu_seeds=("loop_root",),
        max_upstream=0,
        max_downstream=1,
        node_budget=5_000,
    ))
    assert result["status"] == "pass"
    regional = [
        item for item in result["terminals"]
        if "selection" in item.get("parameters", {})
    ]
    assert len(regional) > 1
    assert all(item["compile_status"] == "PASS" for item in regional)
    assert all(item["proof_status"] == "PASS" for item in regional)
    assert any(item["realization"] == "cross-tu-composed-schedules" for item in regional)
    assert result["closure"]["stages"]["source_reconstruction"]["status"] == "complete"
    assert result["closure"]["stages"]["physical_identity"]["status"] == "complete"
    assert any(
        node["decision_context"]["quality"] == "region_projected"
        for node in result["lazy_search"]["nodes"]
        if node["action"].get("op") == "select_schedule"
    )
