#!/usr/bin/env python3
"""Normalize canonical terminal ownership in composition-native search traces."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vladder.composition_native import normalize_terminal_ownership
from vladder.schema_registry import validate_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    paths = sorted(args.corpus.rglob("composition-native-search-trace.json"))
    paths += sorted(args.corpus.rglob("composition-native-search-trace.json.gz"))
    traces_changed = terminals_changed = embedded_changed = summaries_changed = failures = 0
    for path in paths:
        try:
            with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
                trace = json.load(source)
            normalized, changes = normalize_terminal_ownership(trace)
            validation = validate_payload("composition-native-search-trace", normalized)
            if validation["status"] != "pass":
                raise ValueError(json.dumps(validation["errors"][:3], sort_keys=True))
            if changes:
                traces_changed += 1
                terminals_changed += changes
                if not args.check:
                    _write(path, normalized)
            embedded = _embedded_search_path(path.parent)
            if embedded is not None:
                search = _read(embedded)
                current = search.get("composition_native_trace", {})
                if current.get("trace_hash") != normalized.get("trace_hash"):
                    embedded_changed += 1
                    if not args.check:
                        search["composition_native_trace"] = normalized
                        _write(embedded, search)
            summary = path.parent / "executable-search-summary.json"
            if summary.is_file() and not args.check and _refresh_summary(summary):
                summaries_changed += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            failures += 1
            print(f"{path}: {error}", file=sys.stderr)
    report = {
        "schema_version": "vladder-composition-terminal-ownership-normalization-v1",
        "trace_count": len(paths),
        "traces_changed": traces_changed,
        "terminals_changed": terminals_changed,
        "embedded_searches_changed": embedded_changed,
        "summaries_changed": summaries_changed,
        "failures": failures,
        "mode": "check" if args.check else "write",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures or args.check and (traces_changed or embedded_changed) else 0


def _write(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.normalize.tmp")
    if path.suffix == ".gz":
        with gzip.open(temporary, "wt", compresslevel=9) as target:
            json.dump(payload, target, sort_keys=True, separators=(",", ":"))
            target.write("\n")
    else:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _read(path: Path) -> dict:
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
        return json.load(source)


def _embedded_search_path(directory: Path) -> Path | None:
    for name in ("executable-search.json.gz", "executable-search.json"):
        path = directory / name
        if path.is_file():
            return path
    return None


def _refresh_summary(path: Path) -> bool:
    summary = json.loads(path.read_text())
    changed = False
    records = []
    for raw in summary.get("compressed_artifacts", ()):
        record = dict(raw)
        artifact = Path(str(record.get("path", "")))
        if not artifact.is_file():
            artifact = path.parent / artifact.name
        if artifact.is_file():
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            size = artifact.stat().st_size
            if record.get("sha256") != digest or record.get("bytes") != size:
                record.update({"path": str(artifact), "sha256": digest, "bytes": size})
                changed = True
        records.append(record)
    if changed:
        summary["compressed_artifacts"] = records
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return changed


if __name__ == "__main__":
    raise SystemExit(main())
