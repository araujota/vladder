#!/usr/bin/env python3
"""Audit composition-native corpus completeness and label authority."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vladder.composition_native import COMPOSITION_TRACE_VERSION, inference_view
from vladder.language_adapter import canonical_hash
from vladder.schema_registry import validate_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    report = audit(args.corpus, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" or args.allow_incomplete and report["status"] == "incomplete" else 1


def audit(corpus: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    expected = {str(item["id"]): str(item["project_id"]) for item in manifest["roots"]}
    paths = sorted(corpus.glob("roots/*/composition-native-search-trace.json"))
    paths += sorted(corpus.glob("roots/*/composition-native-search-trace.json.gz"))
    projects = Counter()
    tiers = Counter()
    terminal_classes = Counter()
    redundancy_classes = Counter()
    canonical_roots = Counter()
    totals = Counter()
    failures = []
    identifiers = set()
    for path in paths:
        identifier = path.parent.name
        if identifier in identifiers:
            continue
        identifiers.add(identifier)
        try:
            with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
                trace = json.load(source)
            validation = validate_payload("composition-native-search-trace", trace)
            if validation["status"] != "pass":
                failures.append({"identifier": identifier, "kind": "schema", "errors": validation["errors"]})
                continue
            if trace["schema_version"] != COMPOSITION_TRACE_VERSION:
                failures.append({"identifier": identifier, "kind": "schema_version"})
            trace_payload = {key: value for key, value in trace.items() if key != "trace_hash"}
            if trace.get("trace_hash") != canonical_hash(trace_payload):
                failures.append({"identifier": identifier, "kind": "trace_hash_mismatch"})
            if not trace["complete"]:
                failures.append({"identifier": identifier, "kind": "incomplete_search"})
            if trace["summary"]["frontier_count"] != len(trace["labels"]):
                failures.append({"identifier": identifier, "kind": "frontier_label_mismatch"})
            frontier_ids = {item["frontier_id"] for item in trace["frontiers"]}
            label_ids = {item["frontier_id"] for item in trace["labels"]}
            if frontier_ids != label_ids:
                failures.append({"identifier": identifier, "kind": "frontier_label_identity_mismatch"})
            for label in trace["labels"]:
                actions = {item["action_id"] for item in label["action_outcomes"]}
                redundancy_classes.update(
                    str(item.get("redundancy_class", "unknown"))
                    for item in label["action_outcomes"]
                )
                if set(label["oracle_action_order"]) != actions:
                    failures.append({"identifier": identifier, "kind": "oracle_order_not_permutation"})
            failures.extend(_audit_lineage(identifier, trace))
            failures.extend(_audit_decisive_summary(identifier, path.parent))
            view = inference_view(trace)
            if "labels" in view or "terminals" in view:
                failures.append({"identifier": identifier, "kind": "outcome_leakage"})
            project = str(trace["root"]["project_id"])
            canonical_roots[(project, str(trace["root"]["canonical_root_hash"]))] += 1
            projects[project] += 1
            totals.update(trace["summary"])
            tiers.update(item["utility_tier"] for item in trace["terminals"])
            terminal_classes.update(item["terminal_class"] for item in trace["terminals"])
        except Exception as error:
            failures.append({"identifier": identifier, "kind": "read", "error": str(error)[:1000]})
    missing = sorted(set(expected) - identifiers)
    extra = sorted(identifiers - set(expected))
    complete = not missing and not extra
    status = "fail" if failures or extra else "pass" if complete else "incomplete"
    summary = {
        "expected_root_count": len(expected), "trace_count": len(identifiers),
        "missing_root_count": len(missing), "failure_count": len(failures),
        "projects": dict(sorted(projects.items())), "utility_tiers": dict(sorted(tiers.items())),
        "terminal_classes": dict(sorted(terminal_classes.items())),
        "redundancy_classes": dict(sorted(redundancy_classes.items())),
        "total_states": totals["state_count"], "total_frontiers": totals["frontier_count"],
        "composition_frontiers": totals["composition_frontier_count"],
        "transpositions": totals["transposition_count"],
        "duplicate_canonical_root_count": sum(count - 1 for count in canonical_roots.values() if count > 1),
    }
    duplicate_canonical_roots = [
        {"project": project, "canonical_root_hash": root_hash, "count": count}
        for (project, root_hash), count in sorted(canonical_roots.items())
        if count > 1
    ]
    return {
        "schema_version": "vladder-composition-native-corpus-audit-v1",
        "status": status, "summary": summary, "missing": missing,
        "unexpected": extra, "failures": failures,
        "duplicate_canonical_roots": duplicate_canonical_roots,
    }


def _audit_lineage(identifier: str, trace: dict) -> list[dict]:
    failures = []
    states = {str(item["state_id"]): item for item in trace["states"]}
    terminals = {str(item["state_id"]): item for item in trace["terminals"]}
    children = {}
    for state in states.values():
        children.setdefault(state.get("parent_state_id"), []).append(str(state["state_id"]))
    memo = {}

    def best_tier(state_id: str, visiting: set[str] | None = None) -> int:
        if state_id in memo:
            return memo[state_id]
        visiting = set() if visiting is None else set(visiting)
        if state_id in visiting:
            return 0
        visiting.add(state_id)
        own = int(str(terminals.get(state_id, {}).get("utility_tier", "U0"))[1:])
        result = max([own, *(best_tier(child, visiting) for child in children.get(state_id, ()))])
        memo[state_id] = result
        return result

    labels = {str(item["frontier_id"]): item for item in trace["labels"]}
    for frontier in trace["frontiers"]:
        outcomes = {
            str(item["action_id"]): item
            for item in labels[str(frontier["frontier_id"])]["action_outcomes"]
        }
        for action in frontier["available_actions"]:
            outcome = outcomes[str(action["action_id"])]
            child = str(outcome.get("child_state_id") or "")
            if child not in states:
                failures.append({
                    "identifier": identifier, "kind": "missing_action_child", "action": action["action_id"],
                })
                continue
            expected = best_tier(child)
            observed = int(str(outcome["best_descendant_tier"])[1:])
            if expected != observed:
                failures.append({
                    "identifier": identifier, "kind": "descendant_tier_mismatch",
                    "action": action["action_id"], "expected": expected, "observed": observed,
                })
    for terminal in terminals.values():
        owner = states.get(str(terminal.get("state_id")), {})
        if owner.get("canonical_of") or owner.get("disposition") in {
            "canonical_duplicate", "verified_equivalent",
        }:
            failures.append({
                "identifier": identifier,
                "kind": "terminal_attached_to_transposed_duplicate",
                "terminal": terminal.get("terminal_id"),
                "state": terminal.get("state_id"),
                "canonical_of": owner.get("canonical_of"),
            })
        cost = terminal.get("search_cost", {})
        if not isinstance(cost, dict) or float(cost.get("evaluation_wall_ms") or 0) <= 0:
            failures.append({
                "identifier": identifier, "kind": "missing_terminal_search_cost",
                "terminal": terminal.get("terminal_id"),
            })
    return failures


def _audit_decisive_summary(identifier: str, directory: Path) -> list[dict]:
    path = directory / "executable-search-summary.json"
    if not path.is_file():
        return []
    failures = []
    summary = json.loads(path.read_text())
    for record in summary.get("compressed_artifacts", ()):
        artifact = Path(str(record.get("path", "")))
        if not artifact.is_file():
            artifact = directory / artifact.name
        if not artifact.is_file():
            failures.append({
                "identifier": identifier, "kind": "missing_decisive_artifact",
                "artifact": str(record.get("path")),
            })
            continue
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != record.get("sha256") or artifact.stat().st_size != record.get("bytes"):
            failures.append({
                "identifier": identifier, "kind": "decisive_artifact_hash_mismatch",
                "artifact": str(artifact),
            })
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
