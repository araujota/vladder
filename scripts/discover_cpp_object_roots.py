#!/usr/bin/env python3
"""Discover additional C++ semantic roots from exact built object symbols."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any


FAMILY_TERMS = (
    ("serialization_codec", ("encode", "decode", "serialize", "parse", "pack", "unpack", "codec")),
    ("stable_compaction", ("compact", "select", "filter", "scatter", "gather", "sparse", "dirty")),
    ("hash_prefetch", ("hash", "bloom", "prefix", "probe", "prefetch", "lookup")),
    ("reduction", ("reduce", "sum", "count", "aggregate", "min", "max", "scan")),
    ("partition_scheduling", ("schedule", "partition", "thread", "task", "batch", "queue")),
    ("cache_authority", ("cache", "retain", "reuse", "resident", "generation", "authority")),
    ("state_transition", ("state", "commit", "rollback", "update", "merge", "apply", "advance")),
    ("representation_conversion", ("convert", "cast", "copy", "transpose", "reshape", "transform")),
    ("simd_block_transform", ("simd", "avx", "sse", "quant", "block", "vector", "tensor")),
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _entry_arguments(entry: dict[str, Any]) -> list[str]:
    arguments = entry.get("arguments")
    if isinstance(arguments, list):
        return [str(value) for value in arguments]
    return shlex.split(str(entry.get("command", "")))


def _object_path(entry: dict[str, Any]) -> Path | None:
    arguments = _entry_arguments(entry)
    if "-o" not in arguments:
        return None
    value = Path(arguments[arguments.index("-o") + 1])
    return value if value.is_absolute() else Path(str(entry["directory"])) / value


def _short_name(demangled: str) -> str | None:
    if "(" in demangled:
        prefix = demangled.split("(", 1)[0]
    else:
        prefix = demangled
    name = prefix.rsplit("::", 1)[-1].strip()
    if not name or "operator" in name or name.startswith(("_GLOBAL_", "__")):
        return None
    if "<" in name:
        name = name.split("<", 1)[0]
    return name or None


def _family(source: Path, demangled: str) -> str:
    text = f"{source} {demangled}".lower()
    for family, terms in FAMILY_TERMS:
        if any(term in text for term in terms):
            return family
    return "bounded_arithmetic"


def _defined_symbols(object_path: Path, nm: str, cxxfilt: str) -> list[tuple[str, str]]:
    completed = subprocess.run(
        [nm, "--defined-only", "--format=posix", str(object_path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        return []
    symbols = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[1] not in {"T", "t"}:
            continue
        symbol = fields[0]
        if "." in symbol or symbol.startswith(("_ZNSt", "_ZNKSt", "_ZSt", "__")):
            continue
        symbols.append(symbol)
    if not symbols:
        return []
    demangled = subprocess.run(
        [cxxfilt], input="\n".join(symbols) + "\n", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if demangled.returncode != 0:
        return []
    names = demangled.stdout.splitlines()
    return list(zip(symbols[: len(names)], names, strict=True))


def discover(args: argparse.Namespace) -> dict[str, Any]:
    manifests = [_read(path) for path in args.manifest]
    excluded = {
        (str(Path(str(root["source"])).resolve()), str(root["function"]))
        for manifest in manifests for root in manifest.get("roots", ())
    }
    commands: dict[tuple[str, str, int], tuple[str, Path, Path, int]] = {}
    for manifest in manifests:
        for root in manifest.get("roots", ()):
            source = Path(str(root["source"])).resolve()
            database = Path(str(root["compile_commands"])).resolve()
            index = int(root["command_index"])
            key = (str(source), str(database), index)
            commands[key] = (str(root["project_id"]), source, database, index)

    nm = shutil.which("llvm-nm-20") or shutil.which("llvm-nm") or shutil.which("nm")
    cxxfilt = shutil.which("llvm-cxxfilt-20") or shutil.which("llvm-cxxfilt") or shutil.which("c++filt")
    if not nm or not cxxfilt:
        raise RuntimeError("llvm-nm/nm and llvm-cxxfilt/c++filt are required")

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen_symbols: set[tuple[str, str]] = set()
    for project, source, database, index in commands.values():
        raw_database = json.loads(database.read_text())
        if not isinstance(raw_database, list) or index >= len(raw_database):
            continue
        entry = raw_database[index]
        if not isinstance(entry, dict):
            continue
        object_path = _object_path(entry)
        if object_path is None or not object_path.is_file():
            continue
        for symbol, demangled in _defined_symbols(object_path, nm, cxxfilt):
            function = _short_name(demangled)
            if function is None or (str(source), function) in excluded:
                continue
            symbol_key = (str(source), symbol)
            if symbol_key in seen_symbols:
                continue
            seen_symbols.add(symbol_key)
            family = _family(source, demangled)
            identity = hashlib.sha256(
                f"{project}\0{source}\0{symbol}".encode()
            ).hexdigest()[:16]
            grouped[(project, family)].append({
                "id": f"{project}-object-{identity}",
                "project_id": project,
                "language": "cpp",
                "source": str(source),
                "function": function,
                "symbol": symbol,
                "compile_commands": str(database),
                "command_index": index,
                "family": "auto",
                "contract": {"max_selected_build_regions": args.max_selected_build_regions},
                "workload": {
                    "campaign": args.project_id,
                    "selection": "strong-object-symbol-cpp",
                    "source_family": family,
                },
            })

    roots: list[dict[str, Any]] = []
    for group in sorted(grouped):
        choices = sorted(grouped[group], key=lambda item: item["id"])
        roots.extend(choices[: args.per_family])
    roots.sort(key=lambda item: (item["project_id"], item["workload"]["source_family"], item["id"]))
    if not roots:
        raise ValueError("no additional strong object symbols were discovered")
    first_by_project: dict[str, str] = {}
    for root in roots:
        first_by_project.setdefault(str(root["project_id"]), str(root["id"]))
    return {
        "schema_version": "vladder-executable-search-manifest-v1",
        "project_id": args.project_id,
        "mode": "shadow_exhaustive",
        "node_budget": args.node_budget,
        "workers": args.root_workers,
        "terminal_workers": args.terminal_workers,
        "cache_directory": str(args.cache_directory.resolve()),
        "emit_training_v3": True,
        "artifact_retention": "decisive",
        "full_artifact_identifiers": [first_by_project[key] for key in sorted(first_by_project)],
        "roots": roots,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-id", default="cpp-object-symbol-tranche")
    parser.add_argument("--per-family", type=int, default=8)
    parser.add_argument("--node-budget", type=int, default=12000)
    parser.add_argument("--root-workers", type=int, default=3)
    parser.add_argument("--terminal-workers", type=int, default=2)
    parser.add_argument("--max-selected-build-regions", type=int, default=3)
    parser.add_argument("--cache-directory", type=Path, required=True)
    args = parser.parse_args()
    if min(
        args.per_family, args.root_workers, args.terminal_workers,
        args.max_selected_build_regions,
    ) < 1:
        parser.error("budgets and worker counts must be positive")
    result = discover(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "roots": len(result["roots"]),
        "projects": dict(Counter(root["project_id"] for root in result["roots"])),
        "families": dict(Counter(root["workload"]["source_family"] for root in result["roots"])),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
