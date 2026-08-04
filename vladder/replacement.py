from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .extractor import extract_function
from .toolchain import discover_toolchain, run


def _normalized_function(source: str, function: str) -> str:
    extracted = extract_function(source, function)
    renamed = extracted.renamed("__vladder_verified_function")
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", "", renamed, flags=re.DOTALL)
    return re.sub(r"\s+", "", without_comments)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_applied_replacement(
    report_path: Path,
    source_path: Path,
    function: str,
    compile_args: tuple[str, ...] = (),
) -> dict[str, Any]:
    report_path = report_path.resolve()
    source_path = source_path.resolve()
    report = json.loads(report_path.read_text())
    expected_path = report_path.parent / "optimized.c"
    winner = report.get("winner") if isinstance(report.get("winner"), dict) else {}
    promotion = report.get("promotion") if isinstance(report.get("promotion"), dict) else {}
    reasons: list[str] = []
    if not promotion.get("promotable"):
        reasons.append("optimization report does not authorize promotion")
    if not expected_path.exists():
        reasons.append("optimized.c is absent from the proof bundle")

    expected_hash = None
    applied_hash = None
    if expected_path.exists():
        expected = _normalized_function(expected_path.read_text(), function)
        applied = _normalized_function(source_path.read_text(), function)
        expected_hash = _sha256(expected)
        applied_hash = _sha256(applied)
        if expected_hash != applied_hash:
            reasons.append("applied function does not match the proved generated function")

    tc = discover_toolchain()
    language = "c++" if source_path.suffix.lower() in {".cc", ".cpp", ".cxx", ".c++"} else "c"
    standard = "-std=c++20" if language == "c++" else "-std=c17"
    syntax = run([tc.compiler, standard, "-fsyntax-only", *compile_args, str(source_path)], timeout=120)
    if syntax.returncode != 0:
        reasons.append("applied source failed compiler syntax/type checking")

    proof = winner.get("proof") if isinstance(winner.get("proof"), dict) else {}
    memory = winner.get("memory_proof") if isinstance(winner.get("memory_proof"), dict) else {}
    alive2 = winner.get("alive2") if isinstance(winner.get("alive2"), dict) else {}
    evidence = {
        "schema_or_smt": proof.get("status", "missing"),
        "memory": memory.get("status", "missing"),
        "alive2": alive2.get("status", "missing"),
        "differential": winner.get("status", "missing"),
    }
    for name, actual, required in (
        ("schema/SMT", evidence["schema_or_smt"], "PROVED"),
        ("memory", evidence["memory"], "proved"),
        ("Alive2", evidence["alive2"], "correct"),
        ("differential", evidence["differential"], "PASS"),
    ):
        if actual != required:
            reasons.append(f"required {name} evidence is {actual}")

    return {
        "schema_version": "vladder-applied-replacement-v1",
        "status": "pass" if not reasons else "fail",
        "source": str(source_path),
        "function": function,
        "report": str(report_path),
        "candidate": winner.get("candidate"),
        "expected_function_sha256": expected_hash,
        "applied_function_sha256": applied_hash,
        "function_identity": expected_hash is not None and expected_hash == applied_hash,
        "compile": {
            "compiler": tc.compiler,
            "language": language,
            "arguments": list(compile_args),
            "returncode": syntax.returncode,
            "stderr": syntax.stderr[-4000:],
        },
        "proof_chain": evidence,
        "reasons": reasons,
    }
