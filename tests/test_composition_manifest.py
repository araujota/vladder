from __future__ import annotations

import gzip
import json
from pathlib import Path

from scripts.build_composition_native_manifest import build_manifest


def test_composition_manifest_prefers_wide_deep_roots(tmp_path: Path) -> None:
    manifests = []
    progress = []
    for project in ("duckdb", "llama.cpp", "rocksdb"):
        source = tmp_path / f"{project}.cpp"
        source.write_text("int f() { return 0; }\n")
        manifest = tmp_path / f"{project}-manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "vladder-executable-search-manifest-v1",
            "roots": [{"id": f"{project}-root", "project_id": project, "source": str(source), "contract": {}}],
        }))
        result_path = tmp_path / f"{project}-result.json.gz"
        with gzip.open(result_path, "wt") as target:
            json.dump({"lazy_search": {
                "nodes": [{"depth": 3, "stage": "composition"}],
                "frontier_decisions": [{"frontier": [{}, {}, {}, {}]}],
                "canonicalized": 1,
            }}, target)
        progress_path = tmp_path / f"{project}-progress.json"
        progress_path.write_text(json.dumps({"records": [{
            "identifier": f"{project}-root",
            "status": "pass",
            "branch_count": 8,
            "labels": {"KEEP": 2},
            "artifact_compaction": {"compressed_artifacts": [{"path": str(result_path)}]},
        }]}))
        manifests.append(manifest)
        progress.append(progress_path)
    result, audit = build_manifest(tuple(manifests), tuple(progress), roots_per_project=1)
    assert len(result["roots"]) == 3
    assert audit["summary"]["roots_per_project"] == {"duckdb": 1, "llama.cpp": 1, "rocksdb": 1}
    assert all("max_selected_build_regions" not in root["contract"] for root in result["roots"])
