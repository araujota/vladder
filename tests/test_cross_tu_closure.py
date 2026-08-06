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


def _fixture(tmp_path: Path) -> Path:
    sources = {
        "helper.cpp": 'extern "C" int external_authority(int);\nextern "C" int helper(int x) { return external_authority(x) + 3; }\n',
        "root.cpp": 'extern "C" int helper(int);\nextern "C" int root(int x) { return helper(x) + 1; }\n',
        "caller.cpp": 'extern "C" int root(int);\nextern "C" int caller(int x) { return root(x) * 2; }\n',
        "callback.cpp": 'extern "C" int invoke_cb(int (*cb)(int), int x) { return cb(x); }\n',
        "owner.cpp": '#include <cstdlib>\nvolatile void *owner_sink;\nextern "C" int own() { void *p = std::malloc(4); owner_sink = p; if (!p) return 0; std::free(p); return 1; }\n',
    }
    entries = []
    for name, source in sources.items():
        path = tmp_path / name
        path.write_text(source)
        output = tmp_path / f"{name}.o"
        arguments = ["clang-20", "-std=c++20", "-O2", "-c", str(path), "-o", str(output)]
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
    entries = []
    for name in ("weak_a.cpp", "weak_b.cpp"):
        path = tmp_path / name
        path.write_text('extern "C" __attribute__((weak)) int shared_weak() { return 7; }\n')
        output = tmp_path / f"{name}.o"
        arguments = ["clang-20", "-c", str(path), "-o", str(output)]
        subprocess.run(arguments, check=True, capture_output=True, text=True)
        entries.append({"directory": str(tmp_path), "file": str(path), "output": str(output), "arguments": arguments})
    database = tmp_path / "compile_commands.json"
    database.write_text(json.dumps(entries))
    index = WholeBuildIndex.from_compilation_database(database)
    assert index.resolve_definition("shared_weak")["status"] == "ambiguous_odr"
    summaries = CrossTUSummaryDatabase(index, tmp_path / "ambiguous-db")
    assert summaries.summary("shared_weak") is None
