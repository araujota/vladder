#!/usr/bin/env python3
"""Build a deterministic, family-stratified C++ executable-search campaign."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _root_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(Path(str(item["source"])).resolve()),
        str(item["function"]),
    )


def _priority(item: dict[str, Any], seed: str) -> str:
    material = "\0".join(str(part) for part in (
        seed,
        str(item.get("project", item.get("project_id", "unknown"))),
        *_root_key(item),
    ))
    return hashlib.sha256(material.encode()).hexdigest()


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    selection = _read(args.selection)
    regions = selection.get("regions")
    if not isinstance(regions, list):
        raise ValueError("selection must contain a regions array")

    excluded: set[tuple[str, str]] = set()
    for path in args.exclude_manifest:
        manifest = _read(path)
        for item in manifest.get("roots", []):
            if isinstance(item, dict) and item.get("source") and item.get("function"):
                excluded.add(_root_key(item))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen = set(excluded)
    for item in regions:
        if not isinstance(item, dict) or not item.get("source") or not item.get("function"):
            continue
        key = _root_key(item)
        if key in seen:
            continue
        seen.add(key)
        project = str(item.get("project", "unknown"))
        family = str(item.get("primary_family", "unclassified"))
        grouped[(project, family)].append(item)

    selected: list[dict[str, Any]] = []
    for group in sorted(grouped):
        choices = sorted(grouped[group], key=lambda item: _priority(item, args.seed))
        selected.extend(choices[: args.per_family])
    selected.sort(key=lambda item: (
        str(item.get("project", "unknown")),
        str(item.get("primary_family", "unclassified")),
        _priority(item, args.seed),
    ))

    roots = []
    for item in selected:
        roots.append({
            "id": str(item["id"]),
            "project_id": str(item.get("project", "unknown")),
            "language": "cpp",
            "source": str(Path(str(item["source"])).resolve()),
            "function": str(item["function"]),
            "source_line": int(item["line"]),
            "compile_commands": str(Path(str(item["compile_commands"])).resolve()),
            "command_index": int(item["command_index"]),
            "family": "auto",
            "contract": {
                "max_selected_build_regions": args.max_selected_build_regions,
            },
            "workload": {
                "campaign": args.project_id,
                "selection": "family-stratified-cpp",
                "source_family": str(item.get("primary_family", "unclassified")),
            },
        })
    if not roots:
        raise ValueError("selection produced no roots")
    full_artifact_identifiers: list[str] = []
    if args.artifact_retention == "decisive":
        by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for root in roots:
            by_project[str(root["project_id"])].append(root)
        for project in sorted(by_project):
            full_artifact_identifiers.extend(
                str(root["id"])
                for root in by_project[project][: args.full_artifact_roots_per_project]
            )
    return {
        "schema_version": "vladder-executable-search-manifest-v1",
        "project_id": args.project_id,
        "mode": "shadow_exhaustive",
        "node_budget": args.node_budget,
        "workers": args.root_workers,
        "terminal_workers": args.terminal_workers,
        "cache_directory": str(args.cache_directory.resolve()),
        "emit_training_v3": True,
        "artifact_retention": args.artifact_retention,
        "full_artifact_identifiers": full_artifact_identifiers,
        "roots": roots,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-manifest", type=Path, action="append", default=[])
    parser.add_argument("--project-id", default="cpp-family-stratified")
    parser.add_argument("--seed", default="vladder-cpp-search-v1")
    parser.add_argument("--per-family", type=int, default=8)
    parser.add_argument("--node-budget", type=int, default=12000)
    parser.add_argument("--root-workers", type=int, default=6)
    parser.add_argument("--terminal-workers", type=int, default=4)
    parser.add_argument("--max-selected-build-regions", type=int, default=3)
    parser.add_argument(
        "--artifact-retention", choices=("full", "decisive"), default="decisive",
    )
    parser.add_argument("--full-artifact-roots-per-project", type=int, default=1)
    parser.add_argument("--cache-directory", type=Path, required=True)
    args = parser.parse_args()
    if (
        args.per_family < 1 or args.root_workers < 1 or args.terminal_workers < 1
        or args.max_selected_build_regions < 1
        or args.full_artifact_roots_per_project < 0
    ):
        parser.error("worker and per-family counts must be positive")

    manifest = build_manifest(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    projects = Counter(item["project_id"] for item in manifest["roots"])
    families = Counter(item["workload"]["source_family"] for item in manifest["roots"])
    print(json.dumps({
        "output": str(args.output.resolve()),
        "roots": len(manifest["roots"]),
        "projects": dict(sorted(projects.items())),
        "families": dict(sorted(families.items())),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
