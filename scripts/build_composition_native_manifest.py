#!/usr/bin/env python3
"""Select composition-heavy C++ roots from completed exhaustive campaign evidence."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vladder.language_adapter import canonical_hash


TEMP_ROOT = Path(tempfile.gettempdir())

DEFAULT_MANIFESTS = (
    TEMP_ROOT / "vladder-rc24-cpp-expanded-manifest-v17.json",
    TEMP_ROOT / "vladder-rc24-cpp-expanded-manifest-v18-tranche2.json",
    TEMP_ROOT / "vladder-rc24-cpp-object-tranche3.json",
    TEMP_ROOT / "vladder-rc24-cpp-topup-t1-t3-final.json",
)
DEFAULT_PROGRESS = (
    TEMP_ROOT / "vladder-cpp-expanded-exhaustive-v18-cpp-primary/training-v3/training-v3-progress.json",
    TEMP_ROOT / "vladder-cpp-expanded-exhaustive-v18-tranche2/training-v3/training-v3-progress.json",
    TEMP_ROOT / "vladder-cpp-object-exhaustive-v19-tranche3/training-v3/training-v3-progress.json",
    TEMP_ROOT / "vladder-cpp-topup-t1-t3-v20/training-v3/training-v3-progress.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="append", type=Path, default=[])
    parser.add_argument("--progress", action="append", type=Path, default=[])
    parser.add_argument("--roots-per-project", type=int, default=40)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    manifests = tuple(args.manifest) or DEFAULT_MANIFESTS
    progress = tuple(args.progress) or DEFAULT_PROGRESS
    result, audit = build_manifest(manifests, progress, roots_per_project=args.roots_per_project)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    audit_path = args.audit or args.output.with_name(args.output.stem + "-selection-audit.json")
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit["summary"], indent=2, sort_keys=True))
    return 0


def build_manifest(
    manifest_paths: tuple[Path, ...],
    progress_paths: tuple[Path, ...],
    *,
    roots_per_project: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if roots_per_project <= 0:
        raise ValueError("roots_per_project must be positive")
    roots: dict[str, dict[str, Any]] = {}
    template: dict[str, Any] = {}
    for path in manifest_paths:
        raw = json.loads(path.read_text())
        template.update({key: value for key, value in raw.items() if key != "roots"})
        for root in raw.get("roots", ()):
            roots.setdefault(str(root["id"]), dict(root))
    evidence: dict[str, dict[str, Any]] = {}
    for path in progress_paths:
        raw = json.loads(path.read_text())
        for record in raw.get("records", ()):
            identifier = str(record.get("identifier", ""))
            if identifier not in roots or record.get("status") != "pass":
                continue
            trace_path = _trace_path(record)
            metrics = _trace_metrics(trace_path) if trace_path else {}
            labels = record.get("labels", {})
            evidence[identifier] = {
                "trace": str(trace_path) if trace_path else None,
                "branch_count": int(record.get("branch_count", 0)),
                "keep_count": int(labels.get("KEEP", 0)),
                "prune_count": int(labels.get("PRUNE_HIGH_CONFIDENCE", 0)),
                **metrics,
            }

    by_project: dict[str, list[tuple[float, str, dict[str, Any]]]] = {}
    for identifier, root in roots.items():
        metrics = evidence.get(identifier)
        if not metrics or not Path(str(root.get("source", ""))).is_file():
            continue
        if not _composition_eligible(metrics):
            continue
        score = _score(metrics)
        project = _project_name(str(root.get("project_id", "unknown")))
        by_project.setdefault(project, []).append((score, identifier, metrics))
    selected = []
    rows = []
    for project in ("duckdb", "llama.cpp", "rocksdb"):
        values = sorted(by_project.get(project, ()), key=lambda item: (-item[0], item[1]))
        selected_semantic_roots: set[str] = set()
        selected_project_count = 0
        for score, identifier, metrics in values:
            semantic_root_hash = str(metrics.get("semantic_root_hash", ""))
            if semantic_root_hash and semantic_root_hash in selected_semantic_roots:
                continue
            if semantic_root_hash:
                selected_semantic_roots.add(semantic_root_hash)
            root = dict(roots[identifier])
            root["id"] = f"{identifier}-composition-native-{canonical_hash({'id': identifier})[:8]}"
            root["project_id"] = project
            root["contract"] = dict(root.get("contract", {}))
            root["workload"] = {
                **dict(root.get("workload", {})),
                "campaign": "composition-native-rc26",
                "selection": "composition-frontier-evidence",
                "parent_root": identifier,
                "composition_score": score,
            }
            selected.append(root)
            rows.append({"project": project, "parent_root": identifier, "score": score, **metrics})
            selected_project_count += 1
            if selected_project_count >= roots_per_project:
                break
    result = {
        "schema_version": template.get("schema_version", "vladder-executable-search-manifest-v1"),
        "project_id": "composition-native-rc26",
        "mode": "exhaustive",
        "node_budget": max(20_000, int(template.get("node_budget", 0))),
        "workers": 4,
        "terminal_workers": 3,
        "emit_training_v3": True,
        "artifact_retention": "decisive",
        "cache_directory": str(TEMP_ROOT / "vladder-composition-native-cache"),
        "full_artifact_identifiers": [
            min(
                (item for item in selected if item["project_id"] == project),
                key=lambda item: (
                    int(evidence[str(item["workload"]["parent_root"])].get("branch_count", 0)),
                    item["id"],
                ),
                default={"id": ""},
            )["id"]
            for project in ("duckdb", "llama.cpp", "rocksdb")
        ],
        "roots": selected,
    }
    summary = {
        "selected_root_count": len(selected),
        "roots_per_project": {
            project: sum(item["project_id"] == project for item in selected)
            for project in ("duckdb", "llama.cpp", "rocksdb")
        },
        "eligible_root_count": sum(len(items) for items in by_project.values()),
        "minimum_frontier_width": min((item["max_frontier_width"] for item in rows), default=0),
        "maximum_search_depth": max((item["max_depth"] for item in rows), default=0),
        "selection_hash": canonical_hash(rows),
    }
    return result, {"schema_version": "vladder-composition-root-selection-v1", "summary": summary, "roots": rows}


def _trace_path(record: dict[str, Any]) -> Path | None:
    for item in record.get("artifact_compaction", {}).get("compressed_artifacts", ()):
        path = Path(str(item.get("path", "")))
        if path.is_file() and (
            path.name == "executable-search.json.gz" or path.name.endswith("-result.json.gz")
        ):
            return path
    return None


def _trace_metrics(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt") as source:
        result = json.load(source)
    lazy = result.get("lazy_search", {})
    nodes = lazy.get("nodes", ())
    frontiers = lazy.get("frontier_decisions", ())
    widths = [len(item.get("frontier", ())) for item in frontiers]
    depth = max((int(item.get("depth", 0)) for item in nodes), default=0)
    composition_nodes = sum(
        int(item.get("depth", 0)) >= 2
        or str(item.get("stage", "")) in {"composition", "partial_candidate", "candidate"}
        for item in nodes
    )
    return {
        "semantic_root_hash": str(result.get("root", {}).get("semantic_hash", "")),
        "state_count": len(nodes),
        "frontier_count": len(frontiers),
        "max_frontier_width": max(widths, default=0),
        "wide_frontier_count": sum(width >= 4 for width in widths),
        "max_depth": depth,
        "composition_node_count": composition_nodes,
        "canonicalized": int(lazy.get("canonicalized", 0)),
    }


def _composition_eligible(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics.get("max_frontier_width", 0) >= 4
        or metrics.get("max_depth", 0) >= 3
        or metrics.get("wide_frontier_count", 0) >= 1
        or metrics.get("canonicalized", 0) >= 1
    )


def _score(metrics: dict[str, Any]) -> float:
    return (
        6.0 * min(int(metrics.get("max_frontier_width", 0)), 16)
        + 10.0 * min(int(metrics.get("max_depth", 0)), 8)
        + 4.0 * min(int(metrics.get("wide_frontier_count", 0)), 10)
        + 0.1 * min(int(metrics.get("composition_node_count", 0)), 500)
        + 0.2 * min(int(metrics.get("keep_count", 0)), 100)
        + 2.0 * min(int(metrics.get("canonicalized", 0)), 20)
    )


def _project_name(value: str) -> str:
    return "llama.cpp" if value in {"llama", "llama_cpp", "llama.cpp"} else value


if __name__ == "__main__":
    raise SystemExit(main())
