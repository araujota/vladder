#!/usr/bin/env python3
"""Build a non-overlapping selected-region top-up for C++ search supervision."""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def _load_search(root: Path) -> dict[str, Any] | None:
    plain = root / "executable-search.json"
    compressed = root / "executable-search.json.gz"
    try:
        if plain.is_file():
            return json.loads(plain.read_text())
        if compressed.is_file():
            with gzip.open(compressed, "rt") as stream:
                return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _positive_count(record: dict[str, Any]) -> int:
    count = 0
    paths = record.get("bundles") or ([record["bundle"]] if record.get("bundle") else [])
    for path in paths:
        bundle = json.loads(Path(str(path)).read_text())
        for branch in bundle.get("branches", ()):
            surface = next((
                str(item.get("value"))
                for item in branch.get("action", {}).get("categorical_parameters", ())
                if item.get("name") == "decision_surface"
            ), None)
            if (
                not branch.get("baseline")
                and surface not in {"deterministic", "canonicalized", "synthetic_wrapper"}
                and branch.get("survival", {}).get("class") == "KEEP"
            ):
                count += 1
    return count


def _selected_contract(search: dict[str, Any]) -> dict[str, Any] | None:
    for item in search.get("root", {}).get("contract", {}).get("family_contracts", ()):
        if item.get("dispatch_family") == "selected-build-cpp":
            contract = item.get("contract")
            return dict(contract) if isinstance(contract, dict) else None
    return None


def _alternative_domains(
    selected: Iterable[str], omitted: Iterable[str], width: int, limit: int,
) -> tuple[tuple[str, ...], ...]:
    original = tuple(str(item) for item in selected)
    omitted_set = frozenset(str(item) for item in omitted)
    available = tuple(dict.fromkeys((*original, *sorted(omitted_set))))
    selected_width = min(max(1, width), len(available))
    candidates = [
        choice for choice in combinations(available, selected_width)
        if choice != original and omitted_set.intersection(choice)
    ]
    candidates.sort(key=lambda choice: (-len(omitted_set.intersection(choice)), choice))
    return tuple(candidates[:limit])


def build_manifest(
    manifests: list[Path], progresses: list[Path], roots_directories: list[Path],
    *, campaign: str, cache_directory: Path, region_width: int,
    variants_per_root: int, minimum_positive: int, terminal_workers: int = 2,
    max_roots: int | None = None,
) -> dict[str, Any]:
    if not (len(manifests) == len(progresses) == len(roots_directories)):
        raise ValueError("each manifest requires one progress file and roots directory")
    roots: list[dict[str, Any]] = []
    skipped = Counter()
    for manifest_path, progress_path, roots_directory in zip(
        manifests, progresses, roots_directories, strict=True,
    ):
        manifest = json.loads(manifest_path.read_text())
        source_roots = {str(item["id"]): dict(item) for item in manifest["roots"]}
        progress = json.loads(progress_path.read_text())
        for record in progress.get("records", ()):
            identifier = str(record.get("identifier", ""))
            source = source_roots.get(identifier)
            if source is None or record.get("status") != "pass":
                skipped["missing_or_failed_record"] += 1
                continue
            positives = _positive_count(dict(record))
            if positives < minimum_positive:
                skipped["insufficient_positive_lineage"] += 1
                continue
            search = _load_search(roots_directory / identifier)
            contract = _selected_contract(search or {})
            if contract is None:
                skipped["no_selected_build_contract"] += 1
                continue
            selected = tuple(str(item) for item in contract.get("selected_regions", ()))
            omitted = tuple(str(item) for item in contract.get("omitted_regions", ()))
            alternatives = _alternative_domains(
                selected, omitted, region_width, variants_per_root,
            )
            if not alternatives:
                skipped["no_alternative_region_domain"] += 1
                continue
            for choice in alternatives:
                suffix = hashlib.sha256("\0".join(choice).encode()).hexdigest()[:10]
                root = dict(source)
                root["id"] = f"{identifier}-topup-{suffix}"
                root["contract"] = {
                    **dict(source.get("contract") or {}),
                    "selected_build_regions": list(choice),
                    "max_selected_build_regions": len(choice),
                }
                root["workload"] = {
                    **dict(source.get("workload") or {}),
                    "campaign": campaign,
                    "selection": "useful-descendant-alternate-selected-region-domain",
                    "parent_root": identifier,
                    "parent_model_eligible_positive_count": positives,
                    "selected_build_regions": list(choice),
                }
                roots.append(root)
    roots.sort(key=lambda item: str(item["id"]))
    available_root_count = len(roots)
    if max_roots is not None:
        if max_roots < 1:
            raise ValueError("max_roots must be positive")
        roots = roots[:max_roots]
    full: list[str] = []
    seen_projects: set[str] = set()
    for root in roots:
        project = str(root["project_id"])
        if project not in seen_projects:
            full.append(str(root["id"]))
            seen_projects.add(project)
    return {
        "schema_version": "vladder-executable-search-manifest-v1",
        "project_id": campaign,
        "mode": "shadow_exhaustive",
        "workers": 2,
        "terminal_workers": max(1, terminal_workers),
        "node_budget": 12000,
        "cache_directory": str(cache_directory.resolve()),
        "emit_training_v3": True,
        "artifact_retention": "decisive",
        "full_artifact_identifiers": full,
        "selection_audit": {
            "policy": "completed useful roots with alternate explicit selected-build domains",
            "region_width": region_width,
            "variants_per_root": variants_per_root,
            "minimum_model_eligible_positive": minimum_positive,
            "available_root_count": available_root_count,
            "selected_root_count": len(roots),
            "skipped": dict(sorted(skipped.items())),
        },
        "roots": roots,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--progress", type=Path, action="append", required=True)
    parser.add_argument("--roots-directory", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--cache-directory", type=Path, required=True)
    parser.add_argument("--region-width", type=int, default=3)
    parser.add_argument("--variants-per-root", type=int, default=1)
    parser.add_argument("--minimum-positive", type=int, default=1)
    parser.add_argument("--terminal-workers", type=int, default=2)
    parser.add_argument("--max-roots", type=int)
    args = parser.parse_args()
    result = build_manifest(
        args.manifest, args.progress, args.roots_directory,
        campaign=args.campaign,
        cache_directory=args.cache_directory,
        region_width=args.region_width,
        variants_per_root=args.variants_per_root,
        minimum_positive=args.minimum_positive,
        terminal_workers=args.terminal_workers,
        max_roots=args.max_roots,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "root_count": len(result["roots"]),
        "selection_audit": result["selection_audit"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
