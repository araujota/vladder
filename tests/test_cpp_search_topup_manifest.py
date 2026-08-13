from __future__ import annotations

import gzip
import json
from pathlib import Path

from scripts.build_cpp_search_topup_manifest import build_manifest


def test_topup_manifest_selects_a_distinct_omitted_region_domain(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    progress = tmp_path / "progress.json"
    roots = tmp_path / "roots"
    bundle = tmp_path / "bundle.json"
    root_id = "root-a"
    manifest.write_text(json.dumps({
        "roots": [{
            "id": root_id,
            "project_id": "fixture",
            "source": "/src/example.cpp",
            "function": "transform",
            "language": "cpp",
            "contract": {"max_selected_build_regions": 3},
        }],
    }))
    bundle.write_text(json.dumps({
        "branches": [{
            "baseline": False,
            "action": {"categorical_parameters": [{
                "name": "decision_surface", "value": "learned_eligible",
            }]},
            "survival": {"class": "KEEP"},
        }],
    }))
    progress.write_text(json.dumps({
        "records": [{"identifier": root_id, "status": "pass", "bundles": [str(bundle)]}],
    }))
    root = roots / root_id
    root.mkdir(parents=True)
    payload = {
        "root": {"contract": {"family_contracts": [{
            "dispatch_family": "selected-build-cpp",
            "contract": {
                "selected_regions": ["region-000", "region-001", "region-002"],
                "omitted_regions": ["region-003", "region-004", "region-005"],
            },
        }]}},
    }
    with gzip.open(root / "executable-search.json.gz", "wt") as stream:
        json.dump(payload, stream)

    result = build_manifest(
        [manifest], [progress], [roots], campaign="topup", cache_directory=tmp_path / "cache",
        region_width=3, variants_per_root=1, minimum_positive=1,
    )
    assert len(result["roots"]) == 1
    selected = result["roots"][0]["contract"]["selected_build_regions"]
    assert selected == ["region-003", "region-004", "region-005"]
    assert result["roots"][0]["id"].startswith("root-a-topup-")
    assert result["full_artifact_identifiers"] == [result["roots"][0]["id"]]


def test_topup_manifest_caps_roots_and_records_terminal_workers(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    progress = tmp_path / "progress.json"
    roots = tmp_path / "roots"
    records = []
    source_roots = []
    for index in range(2):
        root_id = f"root-{index}"
        bundle = tmp_path / f"bundle-{index}.json"
        bundle.write_text(json.dumps({
            "branches": [{
                "baseline": False,
                "action": {"categorical_parameters": [{
                    "name": "decision_surface", "value": "learned_eligible",
                }]},
                "survival": {"class": "KEEP"},
            }],
        }))
        records.append({"identifier": root_id, "status": "pass", "bundles": [str(bundle)]})
        source_roots.append({
            "id": root_id,
            "project_id": "fixture",
            "source": f"/src/example-{index}.cpp",
            "function": "transform",
            "language": "cpp",
            "contract": {"max_selected_build_regions": 2},
        })
        root = roots / root_id
        root.mkdir(parents=True)
        payload = {
            "root": {"contract": {"family_contracts": [{
                "dispatch_family": "selected-build-cpp",
                "contract": {
                    "selected_regions": ["region-000", "region-001"],
                    "omitted_regions": ["region-002", "region-003"],
                },
            }]}},
        }
        with gzip.open(root / "executable-search.json.gz", "wt") as stream:
            json.dump(payload, stream)
    manifest.write_text(json.dumps({"roots": source_roots}))
    progress.write_text(json.dumps({"records": records}))

    result = build_manifest(
        [manifest], [progress], [roots], campaign="topup", cache_directory=tmp_path / "cache",
        region_width=2, variants_per_root=1, minimum_positive=1,
        terminal_workers=4, max_roots=1,
    )

    assert len(result["roots"]) == 1
    assert result["terminal_workers"] == 4
    assert result["selection_audit"]["available_root_count"] == 2
    assert result["selection_audit"]["selected_root_count"] == 1
