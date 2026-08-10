from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
from typing import Any, Callable

import yaml

from . import __version__
from .agent_workflow import run_agent_workflow, summarize_report
from .capabilities import GrammarRegistry, load_registry


PLAN_SCHEMA = "vladder-optimization-plan-v1"
CAMPAIGN_SCHEMA = "vladder-optimization-campaign-v1"
PROJECT_EVIDENCE_SCHEMA = "vladder-project-evidence-v1"
RUNNER_SCHEMA = "vladder-physical-runner-v1"
REMOTE_RESULT_SCHEMA = "vladder-remote-result-v1"
PROGRESS_SCHEMA = "vladder-progress-event-v1"
ORCHESTRATOR_REVISION = "evidence-orchestrator-v1"

TERMINAL_STATUSES = (
    "NO_COVERAGE",
    "NO_CANDIDATE",
    "NO_PROOF",
    "NO_BENCHMARK",
    "INTEGRATION_REQUIRED",
    "VERIFIED_REJECTION",
    "PROMOTABLE",
)

LANGUAGE_EXTENSIONS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".rs": "rust",
    ".zig": "zig",
    ".jl": "julia",
    ".comp": "shader",
    ".vert": "shader",
    ".frag": "shader",
    ".glsl": "shader",
    ".spv": "shader",
    ".cu": "gpu",
}

PROOF_BADGES = {
    "none": {
        "badge": "UNPROVED",
        "claim": "No machine-checked semantic equivalence claim is available.",
    },
    "structural": {
        "badge": "STRUCTURAL_ONLY",
        "claim": "Shape, ABI, or binary validity passed; output equivalence is not established.",
    },
    "z3": {
        "badge": "Z3_BOUNDED",
        "claim": "The named bounded bit-vector or state-transition obligations are proved only within their declared model.",
    },
    "alive2": {
        "badge": "LLVM_REFINEMENT_LOCAL",
        "claim": "Alive2 establishes local LLVM refinement; owning wrappers and external protocols remain outside the claim.",
    },
    "differential": {
        "badge": "DIFFERENTIAL_ORACLE",
        "claim": "Tested observables match for the executed corpus; this is not exhaustive equivalence proof.",
    },
    "application": {
        "badge": "APPLICATION_PARITY",
        "claim": "Declared project-level observables pass; undeclared external behavior remains outside the claim.",
    },
    "composed_local": {
        "badge": "COMPOSED_LOCAL_PROOF",
        "claim": "The bounded local region passed its declared SMT, LLVM refinement, memory, and differential obligations; owning wrappers and application protocols remain outside the claim.",
    },
}

FAILURE_CATEGORIES = {
    "missing_tool": "environment_problem",
    "missing_source": "selection_problem",
    "missing_compile_commands": "environment_problem",
    "ambiguous_symbol": "selection_problem",
    "missing_contract": "missing_contract",
    "external_authority": "unsupported_semantics",
    "proof_failed": "verification_rejection",
    "benchmark_regression": "physical_regression",
    "integration_failed": "integration_failure",
}

GLOSSARY = {
    "semantic coverage": "How much of the production behavior is represented by the extracted proof unit.",
    "candidate": "One grammar-bounded alternative realization; generation is not proof or a speedup.",
    "proof": "Machine-checked evidence for an explicitly bounded semantic claim.",
    "physical measurement": "Paired timing or counter evidence from the declared workload and hardware.",
    "application integration": "Evidence that the proved candidate is the implementation exercised by the project oracle.",
    "promotion": "Authorization to retain a source change after every declared semantic and physical gate passes.",
    "external authority": "Behavior controlled by a runtime, driver, OS, callback, or object model outside the local proof unit.",
    "grammar coverage": "Which known implementation families were expressible and executable in the bounded search.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def _relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _path_identity(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.resolve()
    if not resolved.exists():
        return {"path": str(resolved), "exists": False}
    if resolved.is_file():
        return {"path": str(resolved), "exists": True, "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}
    members = []
    metadata_names = {
        "compile_commands.json", "Cargo.toml", "Cargo.lock", "build.zig", "build.zig.zon",
        "Project.toml", "Manifest.toml", "CMakeLists.txt", "Makefile", "makefile",
        "pyproject.toml", "pytest.ini",
    }
    ignored = {".git", "build", "dist", "node_modules", ".venv", "venv", "target", ".cache"}
    for candidate in sorted(resolved.rglob("*")):
        if not candidate.is_file() or any(part in ignored for part in candidate.relative_to(resolved).parts):
            continue
        relative = candidate.relative_to(resolved)
        evidence_script = any(part in {"scripts", "tests", "benchmark", "benchmarks"} for part in relative.parts) and re.search(r"(bench|perf|test|verify|replay|workload)", candidate.name, re.IGNORECASE)
        if candidate.name not in metadata_names and not evidence_script:
            continue
        if candidate.stat().st_size > 2 * 1024 * 1024:
            continue
        members.append({"name": str(relative), "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()})
        if len(members) >= 500:
            break
    return {"path": str(resolved), "exists": True, "members": members}


def _scaffold_override_identity(path: Path, kind: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return {"kind": kind, "invalid_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if not isinstance(raw, dict):
        return None
    if kind == "project_evidence":
        selected = raw.get("selected") if isinstance(raw.get("selected"), dict) else {}
        return {"kind": kind, "selected": selected} if any(value not in (None, [], {}) for value in selected.values()) else None
    if kind == "contract":
        return {"kind": kind, "value": raw} if raw.get("confirmed") is True else None
    serialized = json.dumps(raw, sort_keys=True)
    return {"kind": kind, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} if "TODO_REQUIRED" not in serialized else None


def _extract_function_text(source: str, symbol: str | None) -> str:
    if not symbol:
        return source[:12000]
    leaf = symbol.split("::")[-1].split("(")[0]
    match = re.search(rf"\b{re.escape(leaf)}\s*\([^;{{}}]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{{", source)
    if not match:
        return source[:12000]
    start = max(0, source.rfind("\n", 0, match.start()) + 1)
    brace = source.find("{", match.start())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return source[start:start + 12000]


def classify_region(source: Path | None, symbol: str | None, project: Path) -> dict[str, Any]:
    if source:
        language = LANGUAGE_EXTENSIONS.get(source.suffix.lower(), "unknown")
        confidence = 1.0 if language != "unknown" else 0.2
    else:
        language = "unknown"
        confidence = 0.0
    alternatives: list[dict[str, Any]] = []
    if source and source.suffix.lower() in {".h", ".hpp", ".hh"}:
        alternatives.append({"kind": "cpp", "reason": "header requires a concrete compilation command"})
    if source and source.suffix.lower() == ".cu":
        alternatives.extend([
            {"kind": "gpu", "reason": "CUDA kernel and host orchestration require separate evidence"},
            {"kind": "cpp", "reason": "host-only subregions may close as bounded C++"},
        ])
    kind = language
    if language == "unknown" and (project / "Cargo.toml").exists():
        alternatives.append({"kind": "rust", "reason": "project metadata contains Cargo.toml"})
    if language == "unknown" and (project / "build.zig").exists():
        alternatives.append({"kind": "zig", "reason": "project metadata contains build.zig"})
    return {
        "kind": kind,
        "language": language,
        "confidence": confidence,
        "symbol": symbol,
        "alternatives": alternatives,
        "authority": "routing only; classification is not semantic capture",
    }


_BOUNDARY_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("device_runtime", r"\b(vk[A-Z]\w*|cuda\w*|cu[A-Z]\w*|hip\w*|gl[A-Z]\w*)\s*\(", "external device state and ordering", "bind a device runner with output hash and device timestamps"),
    ("network_io", r"\b(send|sendto|recv|recvfrom|socket|connect|accept|poll|epoll_wait|ibv_\w+)\s*\(", "OS/network protocol effects", "bind exact packet/state observables and a socket or RDMA runner"),
    ("filesystem_io", r"\b(open|read|write|close|fopen|fread|fwrite|fsync|mmap)\s*\(", "filesystem and OS effects", "isolate the pure buffer transformation and retain an I/O integration oracle"),
    ("synchronization", r"\b(std::atomic|atomic_|mutex|lock_guard|unique_lock|condition_variable|futex|barrier)\b", "happens-before and publication semantics", "declare a finite protocol envelope and stress the production synchronization path"),
    ("allocation", r"\b(new|delete|malloc|calloc|realloc|free|make_shared|make_unique|reserve|push_back|emplace_back)\b", "ownership, allocation failure, and object lifetime", "use a no-growth bounded view or generate an owning application adapter"),
    ("callback", r"\b(callback|visitor|handler|co_await|co_yield|std::function)\b", "control leaves the local proof unit", "declare callback effects or isolate a closed callback-free subregion"),
    ("exception_unwind", r"\b(throw|try|catch)\b", "exception result and destructor ordering", "declare error and cleanup observables or isolate a noexcept proof unit"),
    ("foreign_object_model", r"\b(Usd\w*|pxr::|PyObject|JNI\w*|objc_msgSend)\b", "third-party identity, callbacks, and ownership", "retain an application oracle around locally provable projections"),
    ("dynamic_dispatch", r"\b(dynamic_cast|typeid|virtual)\b|->\s*\w+\s*\(", "callee identity may vary at runtime", "bind concrete dynamic types or keep the dispatch shell outside the proof unit"),
)


def inventory_external_authorities(region_text: str) -> list[dict[str, Any]]:
    inventory = []
    for category, pattern, impact, strategy in _BOUNDARY_PATTERNS:
        matches = sorted(set(re.findall(pattern, region_text)))
        if not matches:
            continue
        normalized = [item if isinstance(item, str) else "".join(item) for item in matches]
        inventory.append({
            "category": category,
            "observations": normalized[:20],
            "proof_impact": impact,
            "recommended_strategy": strategy,
            "local_subregions_remain_eligible": True,
        })
    return inventory


def infer_contract(region_text: str, language: str, symbol: str | None) -> dict[str, Any]:
    pointer_like = bool(re.search(r"\*|std::span|\[\]|\bSlice\b|\[\]", region_text))
    floating = bool(re.search(r"\b(float|double|f32|f64|Float32|Float64)\b", region_text))
    loop_count = len(re.findall(r"\b(for|while)\s*\(", region_text)) + len(re.findall(r"\bfor\s+\w+\s+in\b", region_text))
    facts: dict[str, Any] = {
        "symbol": symbol,
        "language": language,
        "bounded_region_candidate": bool(symbol and loop_count <= 8),
        "loop_count": loop_count,
        "noexcept_declared": "noexcept" in region_text if language == "cpp" else None,
        "contiguous_view_observed": bool(re.search(r"std::span|\.data\s*\(|\[[^]]+\]|\bslice\b|Vector\{", region_text)),
        "const_inputs_observed": bool(re.search(r"\bconst\b|span\s*<\s*const|&\[", region_text)),
        "allocation_observed": bool(re.search(r"\b(new|malloc|reserve|push_back|emplace_back|resize)\b", region_text)),
        "floating_point_observed": floating,
        "deterministic_source_shape": not bool(re.search(r"\b(rand|random|clock|time|gettimeofday)\b", region_text)),
    }
    unresolved: list[dict[str, Any]] = []
    if pointer_like:
        unresolved.append({
            "id": "aliasing",
            "question": "Which input and output regions may overlap?",
            "suggested_path": "/contract/aliasing",
            "closest_valid_value": "declare_exact_overlap_matrix",
        })
    if floating:
        unresolved.append({
            "id": "floating_point",
            "question": "Are outputs bitwise exact, IEEE-order equivalent, or tolerance bounded?",
            "suggested_path": "/contract/numerical",
            "closest_valid_value": {"class": "bitwise_exact"},
        })
    if language == "cpp" and "noexcept" not in region_text:
        unresolved.append({
            "id": "exceptions",
            "question": "What exception, cleanup, and allocation-failure behavior is observable?",
            "suggested_path": "/contract/errors",
            "closest_valid_value": "preserve_production_exception_projection",
        })
    unresolved.append({
        "id": "application_observables",
        "question": "Which outputs, state transitions, statuses, and external effects define parity?",
        "suggested_path": "/contract/observables",
        "closest_valid_value": ["return_value", "written_output_extent", "mutated_state"],
    })
    patch = [
        {"op": "add", "path": item["suggested_path"], "value": item["closest_valid_value"]}
        for item in unresolved
    ]
    return {
        "facts": facts,
        "unresolved_assumptions": unresolved,
        "suggested_patch": patch,
        "authority": "candidate contract inferred from syntax; unresolved facts require confirmation",
    }


def _split_cpp_parameters(parameters: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depths = {"<": 0, "(": 0, "[": 0, "{": 0}
    closing = {">": "<", ")": "(", "]": "[", "}": "{"}
    for index, character in enumerate(parameters):
        if character in depths:
            depths[character] += 1
        elif character in closing:
            opener = closing[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == "," and not any(depths.values()):
            parts.append(parameters[start:index].strip())
            start = index + 1
    tail = parameters[start:].strip()
    if tail and tail != "void":
        parts.append(tail)
    return parts


def _cpp_signature_projection(region_text: str, symbol: str | None) -> dict[str, Any]:
    if not symbol:
        return {"captured": False, "parameters": [], "reason": "symbol is required"}
    leaf = symbol.split("::")[-1].split("(")[0]
    match = re.search(rf"\b{re.escape(leaf)}\s*\((?P<parameters>[^;{{}}]*)\)", region_text, re.DOTALL)
    if not match:
        return {"captured": False, "parameters": [], "reason": "bounded source signature was not located"}
    projected = []
    for index, declaration in enumerate(_split_cpp_parameters(match.group("parameters"))):
        declaration = re.sub(r"\s*=.*$", "", declaration).strip()
        name_match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^]]*\])?\s*$", declaration)
        if not name_match:
            projected.append({"declaration": declaration, "name": f"arg{index}", "usable": False})
            continue
        projected.append({"declaration": declaration, "name": name_match.group(1), "usable": True})
    return {
        "captured": bool(projected) and all(item["usable"] for item in projected),
        "parameters": projected,
        "source_signature": region_text[:region_text.find("{")].strip(),
        "reason": None if projected and all(item["usable"] for item in projected) else "one or more parameter names require manual binding",
    }


def _typed_cpp_adapter(plan: dict[str, Any], output_directory: Path) -> Path | None:
    if plan["classification"]["kind"] != "cpp":
        return None
    signature = plan["classification"].get("signature_projection") or {}
    path = output_directory / "application-adapter.hpp"
    if path.exists():
        return path
    parameters = signature.get("parameters", [])
    if not parameters or not all(item.get("usable") for item in parameters):
        path.write_text(
            "#pragma once\n\n"
            "// vLadder could not safely reproduce this source signature.\n"
            "// Bind the production call through application-adapter.yaml; do not infer omitted ownership semantics.\n"
        )
        return path
    declarations = ",\n        ".join(str(item["declaration"]) for item in parameters)
    names = ", ".join(str(item["name"]) for item in parameters)
    symbol = str(plan["classification"].get("symbol") or "region")
    path.write_text(
        "#pragma once\n\n"
        "#include <utility>\n\n"
        "namespace vladder_generated_adapter {\n\n"
        f"// Production region: {symbol}\n"
        "// The caller must clone mutable inputs before paired execution and project every declared observable.\n"
        "template <class ProductionCallable>\n"
        "decltype(auto) run_production(\n"
        "        ProductionCallable&& callable,\n"
        f"        {declarations})\n"
        f"    noexcept(noexcept(std::forward<ProductionCallable>(callable)({names}))) {{\n"
        f"  return std::forward<ProductionCallable>(callable)({names});\n"
        "}\n\n"
        "template <class CandidateCallable>\n"
        "decltype(auto) run_candidate(\n"
        "        CandidateCallable&& callable,\n"
        f"        {declarations})\n"
        f"    noexcept(noexcept(std::forward<CandidateCallable>(callable)({names}))) {{\n"
        f"  return std::forward<CandidateCallable>(callable)({names});\n"
        "}\n\n"
        "// TODO_REQUIRED: define an oracle over return values, mutated arguments, status, and external effects.\n"
        "template <class Oracle, class BaselineObservation, class CandidateObservation>\n"
        "bool equivalent(Oracle&& oracle, const BaselineObservation& baseline, const CandidateObservation& candidate) {\n"
        "  return std::forward<Oracle>(oracle)(baseline, candidate);\n"
        "}\n\n"
        "}  // namespace vladder_generated_adapter\n"
    )
    return path


def discover_project_evidence(project: Path) -> dict[str, Any]:
    project = project.resolve()
    candidates: list[dict[str, Any]] = []

    def add(kind: str, command: list[str], source: str, confidence: float, **extra: Any) -> None:
        key = (kind, tuple(command))
        if any((item["kind"], tuple(item["command"])) == key for item in candidates):
            return
        candidates.append({
            "id": f"{kind}:{len(candidates)}",
            "kind": kind,
            "command": command,
            "source": source,
            "confidence": confidence,
            "binding_status": "candidate_not_authoritative",
            **extra,
        })

    cmake = project / "CMakeLists.txt"
    if cmake.exists():
        text = cmake.read_text(errors="ignore")
        if re.search(r"\b(enable_testing|add_test)\s*\(", text):
            add("correctness_test", ["ctest", "--test-dir", "build", "--output-on-failure"], "CMakeLists.txt", 0.9)
        if re.search(r"benchmark|perf", text, re.IGNORECASE):
            add("benchmark", ["cmake", "--build", "build", "--target", "benchmark"], "CMakeLists.txt", 0.5)
    if (project / "Cargo.toml").exists():
        add("correctness_test", ["cargo", "test", "--workspace"], "Cargo.toml", 0.95)
        if (project / "benches").exists():
            add("benchmark", ["cargo", "bench", "--workspace"], "benches/", 0.9)
    if (project / "build.zig").exists():
        add("correctness_test", ["zig", "build", "test"], "build.zig", 0.85)
        if "bench" in (project / "build.zig").read_text(errors="ignore").lower():
            add("benchmark", ["zig", "build", "bench"], "build.zig", 0.7)
    if (project / "Project.toml").exists():
        add("correctness_test", ["julia", "--project=.", "-e", "using Pkg; Pkg.test()"], "Project.toml", 0.9)
    for make_name in ("Makefile", "makefile"):
        makefile = project / make_name
        if not makefile.exists():
            continue
        text = makefile.read_text(errors="ignore")
        if re.search(r"^test\s*:", text, re.MULTILINE):
            add("correctness_test", ["make", "test"], make_name, 0.85)
        if re.search(r"^(bench|benchmark|perf)\s*:", text, re.MULTILINE):
            target = re.search(r"^(bench|benchmark|perf)\s*:", text, re.MULTILINE).group(1)  # type: ignore[union-attr]
            add("benchmark", ["make", target], make_name, 0.8)
    for config, command in (
        ("pyproject.toml", ["python3", "-m", "pytest"]),
        ("pytest.ini", ["python3", "-m", "pytest"]),
    ):
        if (project / config).exists():
            add("correctness_test", command, config, 0.85)
    scripts = []
    for directory in (project / "scripts", project / "benchmarks", project / "benchmark", project / "tests"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and re.search(r"(bench|perf|test|verify|replay|workload)", path.name, re.IGNORECASE):
                scripts.append(path)
    for path in scripts[:30]:
        command = [str(path)] if os.access(path, os.X_OK) else (["python3", str(path)] if path.suffix == ".py" else [str(path)])
        kind = "benchmark" if re.search(r"bench|perf|workload", path.name, re.IGNORECASE) else "correctness_test"
        add(kind, command, _relative_or_absolute(path, project), 0.55)
        text = path.read_text(errors="ignore")[:200_000]
        field_families = (
            ("observable_field", r"\b(output_hash|observable_hash|result_hash|checksum|digest|sha256)\b"),
            ("metric_field", r"\b(duration_ns|elapsed_ns|latency_ns|cycles|tokens_per_second|throughput|metric)\b"),
            ("counter_field", r"\b(cache_misses|branch_misses|instructions|gpu_timestamp|queue_wait|transfer_bytes)\b"),
        )
        for field_kind, pattern in field_families:
            for field in sorted(set(re.findall(pattern, text, re.IGNORECASE)))[:12]:
                add(
                    field_kind,
                    command,
                    _relative_or_absolute(path, project),
                    0.65,
                    field=str(field),
                    claim_boundary="name match only; bind the field to a declared observable or metric before use",
                )
    compile_commands = next((path for path in (project / "build/compile_commands.json", project / "compile_commands.json") if path.exists()), None)
    return {
        "schema_version": PROJECT_EVIDENCE_SCHEMA,
        "project": str(project),
        "compile_commands": str(compile_commands) if compile_commands else None,
        "candidates": candidates,
        "selected": {
            "correctness_test": None,
            "benchmark": None,
            "observable_hash_field": None,
            "metric_field": None,
            "counter_fields": [],
        },
        "unresolved": [
            "select commands that exercise the production region",
            "declare complete exact or tolerance-bounded observables",
            "declare timing metric and direction",
        ],
        "claim_boundary": "discovery is a setup aid and does not establish parity or representativeness",
    }


def summarize_cross_tu_boundary(
    source: Path | None,
    region_text: str,
    compile_commands: Path | None,
    authorities: list[dict[str, Any]],
) -> dict[str, Any]:
    database_path = compile_commands
    if database_path and database_path.is_dir():
        database_path = database_path / "compile_commands.json"
    entries: list[dict[str, Any]] = []
    if database_path and database_path.exists():
        try:
            raw = json.loads(database_path.read_text())
            if isinstance(raw, list):
                entries = [item for item in raw if isinstance(item, dict)]
        except (ValueError, OSError):
            entries = []
    selected = []
    if source:
        for item in entries:
            candidate = Path(str(item.get("file", "")))
            directory = Path(str(item.get("directory", ".")))
            candidate = candidate if candidate.is_absolute() else directory / candidate
            if candidate.resolve() == source.resolve():
                selected.append(item)
    keywords = {"if", "for", "while", "switch", "return", "sizeof", "alignof", "decltype"}
    calls = sorted({
        call for call in re.findall(r"\b([A-Za-z_]\w*(?:::\w+)*)\s*\(", region_text)
        if call.split("::")[-1] not in keywords
    })
    external_tokens = {str(token) for item in authorities for token in item.get("observations", [])}
    externally_blocked = [call for call in calls if any(token and token in call for token in external_tokens)]
    conditionally_closed = [call for call in calls if call not in externally_blocked]
    return {
        "compile_commands": str(database_path) if database_path else None,
        "translation_unit_match_count": len(selected),
        "compilation_database_entry_count": len(entries),
        "subgraphs": {
            "closed": [{"kind": "local_expression_and_control", "count": len(re.findall(r"[=+*\-&|^]|\b(if|for|while|switch)\b", region_text))}],
            "conditionally_closed": [{"callee": call, "condition": "requires helper summary or inlining"} for call in conditionally_closed],
            "externally_blocked": [
                {"category": item["category"], "proof_impact": item["proof_impact"], "strategy": item["recommended_strategy"]}
                for item in authorities
            ],
        },
        "closure_status": (
            "compile_command_missing" if not selected and source and source.suffix.lower() in {".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"} else
            "externally_scoped" if authorities else
            "local_helpers_require_summary" if conditionally_closed else
            "locally_closed_candidate"
        ),
        "authority": "early boundary inventory; execution-time AST/IR and whole-build closure supersede this report",
    }


def _recognize_families(region_text: str) -> list[dict[str, Any]]:
    rules = (
        ("deep-information-realization", r"popcount|bit_count|uint8|unsigned char|byte|mask"),
        ("expression-algebra", r"[+*\-&|^]|\bmin\b|\bmax\b|\bselect\b"),
        ("control-flow", r"\bif\b|\bswitch\b|\?"),
        ("loop-schedule", r"\bfor\b|\bwhile\b"),
        ("memory-alias", r"\*|std::span|\.data\s*\(|\[[^]]+\]"),
        ("reductions-scans", r"\b(sum|count|reduce|scan|prefix|max|min|histogram)\b"),
        ("layout-representation", r"struct|AoS|SoA|interleav|pack"),
        ("materialization-fusion", r"temporary|scratch|vector|buffer|intermediate"),
        ("state-window", r"ring|window|rolling|state"),
        ("concurrency-memory-order", r"atomic|mutex|lock|queue|publish|commit|rollback"),
        ("specialization-dispatch", r"dispatch|alignment|batch|context|isa"),
        ("lifetime-realization", r"cache|serialize|decode|validate|generation|retain|invalidate"),
        ("bounded-variable-output-dataflow", r"copy_if|compact|changed|dirty|push_back|prefix|codec|quantiz|packet"),
        ("typed-spirv-core", r"gl_|image|subgroup|spirv|shader"),
        ("heterogeneous-algorithm-orchestration", r"cuda|vulkan|gpu|queue|presentation"),
        ("finite-resource-protocol", r"socket|descriptor|resource|owner|publish|retire"),
        ("structured-stateful-dataflow", r"delta|sparse|cache|transaction|ack|revision"),
    )
    return [
        {"family": family, "evidence": sorted(set(re.findall(pattern, region_text, re.IGNORECASE)))[:8]}
        for family, pattern in rules if re.search(pattern, region_text, re.IGNORECASE)
    ]


def grammar_coverage(region_text: str, registry: GrammarRegistry) -> dict[str, Any]:
    recognized = _recognize_families(region_text)
    families = []
    for item in recognized:
        family = registry.family(item["family"])
        routes = family.get("source_routes", {})
        families.append({
            **item,
            "status": family.get("status"),
            "coverage": "executable" if routes else "plan_only",
            "executable_rules": sorted(routes),
            "known_rules": list(family.get("rules", [])),
        })
    executable = [item for item in families if item["coverage"] == "executable"]
    plan_only = [item for item in families if item["coverage"] == "plan_only"]
    return {
        "grammar_version": registry.version,
        "grammar_sha256": registry.sha256,
        "recognized_families": families,
        "executable_family_count": len(executable),
        "plan_only_family_count": len(plan_only),
        "coverage_classification": (
            "no_recognized_family" if not families else
            "partial_executable" if plan_only else
            "recognized_families_executable"
        ),
        "negative_result_authority": "grammar_limited_negative" if plan_only or not families else "eligible_for_grammar_exhaustion_after_measurement",
    }


def representativeness(region_text: str, authorities: list[dict[str, Any]], workload_share: float | None) -> dict[str, Any]:
    calls = re.findall(r"\b([A-Za-z_]\w*(?:::\w+)*)\s*\(", region_text)
    control = min(1.0, (len(re.findall(r"\b(if|switch|for|while)\b", region_text)) + 1) / 6.0)
    dataflow = 0.9 if re.search(r"=|return", region_text) else 0.3
    ownership = max(0.1, 1.0 - 0.12 * sum(item["category"] in {"allocation", "foreign_object_model", "callback"} for item in authorities))
    closure = max(0.1, 1.0 - min(0.8, len(set(calls)) / 25.0) - 0.08 * len(authorities))
    workload = min(1.0, max(0.0, (workload_share or 0.0) / 20.0)) if workload_share is not None else 0.0
    dimensions = {
        "dataflow": round(dataflow, 3),
        "ownership": round(ownership, 3),
        "control_flow": round(control, 3),
        "call_closure": round(closure, 3),
        "workload_share": round(workload, 3),
    }
    aggregate = sum(dimensions.values()) / len(dimensions)
    return {
        "dimensions": dimensions,
        "aggregate": round(aggregate, 3),
        "status": "representative_candidate" if aggregate >= 0.7 and min(dimensions.values()) >= 0.3 else "limited_representation",
        "limitations": [name for name, score in dimensions.items() if score < 0.3],
        "authority": "advisory coverage score; cannot promote a candidate",
    }


def _dependency(name: str, *, required: bool, available: bool, remediation: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "required": required,
        "available": available,
        "remediation": remediation,
    }


def forecast_workflow(
    classification: dict[str, Any],
    contract: dict[str, Any],
    authorities: list[dict[str, Any]],
    evidence: dict[str, Any],
    coverage: dict[str, Any],
    compile_commands: Path | None,
) -> dict[str, Any]:
    kind = classification["kind"]
    has_oracle_candidate = any(item["kind"] == "correctness_test" for item in evidence["candidates"])
    has_benchmark_candidate = any(item["kind"] == "benchmark" for item in evidence["candidates"])
    has_bound_oracle = bool(evidence.get("selected", {}).get("correctness_test"))
    has_bound_benchmark = bool(evidence.get("selected", {}).get("benchmark"))
    dependencies = [
        _dependency("clang", required=kind in {"c", "cpp"}, available=bool(shutil.which("clang") or shutil.which("clang-20")), remediation=["vladder", "doctor", "--strict"]),
        _dependency("z3", required=True, available=bool(shutil.which("z3")), remediation=["vladder", "doctor", "--strict"]),
        _dependency("alive-tv", required=kind in {"c", "cpp", "rust", "zig", "julia"}, available=bool(shutil.which("alive-tv")), remediation=["vladder", "doctor", "--strict"]),
        _dependency("compile_commands", required=kind == "cpp", available=bool(compile_commands and compile_commands.exists()), remediation=["cmake", "-S", ".", "-B", "build", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]),
        _dependency("application_oracle", required=True, available=has_bound_oracle, remediation=None),
        _dependency("benchmark_runner", required=True, available=has_bound_benchmark, remediation=None),
    ]
    semantic_probability = 0.95 if kind in {"c", "rust", "zig", "julia"} else 0.72 if kind == "cpp" else 0.55 if kind in {"shader", "gpu"} else 0.2
    semantic_probability *= max(0.25, 1.0 - 0.06 * len(authorities))
    candidate_probability = semantic_probability * (0.85 if coverage["executable_family_count"] else 0.25)
    proof_probability = candidate_probability * (0.78 if shutil.which("z3") else 0.25)
    benchmark_probability = proof_probability * (0.8 if has_benchmark_candidate else 0.35)
    integration_probability = benchmark_probability * (0.75 if has_oracle_candidate else 0.2)
    states = [
        ("semantic_coverage", semantic_probability, kind != "unknown" and (kind != "cpp" or bool(compile_commands and compile_commands.exists()))),
        ("candidate_generation", candidate_probability, coverage["executable_family_count"] > 0),
        ("proof", proof_probability, bool(shutil.which("z3"))),
        ("physical_measurement", benchmark_probability, has_bound_benchmark),
        ("application_integration", integration_probability, has_bound_oracle and has_bound_benchmark),
    ]
    first_unreachable = next((name for name, _, reachable in states if not reachable), None)
    complexity = 1 + len(authorities) + len(contract["unresolved_assumptions"])
    low = 2 if first_unreachable == "semantic_coverage" else 15 + complexity * 5
    high = 15 if first_unreachable == "semantic_coverage" else 180 + complexity * 120
    if kind in {"shader", "gpu"}:
        high *= 2
    return {
        "evidence_states": [
            {"state": name, "reachable": reachable, "probability": round(probability, 3)}
            for name, probability, reachable in states
        ],
        "first_unreachable_state": first_unreachable,
        "dependencies": dependencies,
        "estimated_runtime_seconds": {"low": low, "high": high},
        "estimated_artifact_count": {"low": 8, "high": 18 + complexity * 6},
        "estimated_interpretation_tokens": {"concise": 450, "full_lineage": 2500 + complexity * 300},
        "authority": "forecast only; execution evidence supersedes this estimate",
    }


def economic_decision(
    forecast: dict[str, Any],
    coverage: dict[str, Any],
    represent: dict[str, Any],
    workload_share: float | None,
    minimum_effect: float,
    *,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if summary:
        states = summary.get("states", {})
        if states.get("production_promoted") and states.get("application_integrated"):
            return {"recommendation": "STOP", "reason": "declared optimization objective reached; retain and monitor the promoted candidate"}
        if states.get("production_promoted") and not states.get("application_integrated"):
            return {"recommendation": "CONTINUE", "reason": "local promotion gates passed; bind the proved candidate to the project oracle and composed workload"}
        if states.get("physically_benchmarked") and not states.get("production_promoted"):
            if coverage["negative_result_authority"] == "eligible_for_grammar_exhaustion_after_measurement":
                return {"recommendation": "STOP", "reason": "verified physical search did not meet the promotion floor across recognized executable families"}
            return {"recommendation": "ESCALATE", "reason": "measured negative is grammar-limited; add only an attribution-justified family"}
        if states.get("candidate_proved"):
            return {"recommendation": "CONTINUE", "reason": "proof passed and physical measurement is the next valuable gate"}
    if forecast["first_unreachable_state"] in {"semantic_coverage", "candidate_generation", "proof"}:
        return {"recommendation": "ESCALATE", "reason": f"{forecast['first_unreachable_state']} is not currently reachable; resolve its generated boundary before search"}
    if workload_share is not None and workload_share * 0.25 < minimum_effect:
        return {"recommendation": "STOP", "reason": "optimistic regional gain cannot reach the declared composed-effect floor"}
    if represent["aggregate"] < 0.25:
        return {"recommendation": "ESCALATE", "reason": "proof unit is too weakly representative for application promotion"}
    return {"recommendation": "CONTINUE", "reason": "reachable evidence and plausible composed value justify the next planned stage"}


@dataclass(frozen=True)
class OptimizationRequest:
    project: Path
    source: Path | None
    symbol: str | None
    compile_commands: Path | None
    contract: Path | None
    workload: Path | None
    profile: Path | None
    output_directory: Path
    minimum_effect_percent: float = 1.0
    plan_only: bool = False
    force: bool = False
    verbose: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": str(self.project.resolve()),
            "source": str(self.source.resolve()) if self.source else None,
            "symbol": self.symbol,
            "compile_commands": str(self.compile_commands.resolve()) if self.compile_commands else None,
            "contract": str(self.contract.resolve()) if self.contract else None,
            "workload": str(self.workload.resolve()) if self.workload else None,
            "profile": str(self.profile.resolve()) if self.profile else None,
            "output_directory": str(self.output_directory.resolve()),
            "minimum_effect_percent": self.minimum_effect_percent,
            "plan_only": self.plan_only,
        }


class ProgressWriter:
    def __init__(self, output_directory: Path, *, emit: bool = True) -> None:
        self.path = output_directory / "progress.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.emit = emit

    def write(self, phase: str, percent: int, message: str, *, blocker: str | None = None, artifact: Path | None = None, estimated_remaining_seconds: int | None = None) -> dict[str, Any]:
        event = {
            "schema_version": PROGRESS_SCHEMA,
            "at": _now(),
            "phase": phase,
            "percent": percent,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "estimated_remaining_seconds": estimated_remaining_seconds,
            "message": message,
            "current_blocker": blocker,
            "artifact": str(artifact) if artifact else None,
        }
        with self.path.open("a") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        if self.emit:
            suffix = f" blocker={blocker}" if blocker else ""
            print(f"vLadder [{percent:3d}%] {phase}: {message}{suffix}")
        return event


def _load_workload_share(profile: Path | None, symbol: str | None) -> float | None:
    if not profile or not profile.exists():
        return None
    try:
        raw = json.loads(profile.read_text()) if profile.suffix == ".json" else yaml.safe_load(profile.read_text())
    except (ValueError, yaml.YAMLError):
        return None
    if isinstance(raw, dict):
        for key in ("regional_share_percent", "runtime_share_percent", "share_percent"):
            if isinstance(raw.get(key), (int, float)):
                return float(raw[key])
        regions = raw.get("regions")
        if isinstance(regions, list):
            for item in regions:
                if isinstance(item, dict) and str(item.get("symbol")) == str(symbol):
                    for key in ("regional_share_percent", "runtime_share_percent", "share_percent"):
                        if isinstance(item.get(key), (int, float)):
                            return float(item[key])
    return None


def _plan_steps(kind: str, request: OptimizationRequest, first_unreachable: str | None) -> list[dict[str, Any]]:
    source = str(request.source.resolve()) if request.source else "<source-required>"
    symbol = request.symbol or "<symbol-required>"
    common = ["--source", source, "--function", symbol]
    if kind == "c":
        executor = ["vladder", "region", "optimize", *common, "--out-dir", str(request.output_directory / "execution")]
    elif kind == "cpp":
        database = str(request.compile_commands.resolve()) if request.compile_commands else "<compile-commands-required>"
        action = "isolate" if first_unreachable in {"physical_measurement", "application_integration"} else "optimize"
        executor = ["vladder", "cpp", action, *common, "--compile-commands", database, "--out-dir", str(request.output_directory / "execution")]
    elif kind in {"rust", "zig", "julia"}:
        executor = ["vladder", kind, "optimize", *common, "--out-dir", str(request.output_directory / "execution")]
    elif kind == "shader":
        executor = ["vladder", "shader", "synthesize", "--source", source, "--out-dir", str(request.output_directory / "execution")]
    elif kind == "gpu":
        executor = ["vladder", "gpu", "capture", "--manifest", "<gpu-workflow.yaml>", "--out-dir", str(request.output_directory / "execution")]
    else:
        executor = ["vladder", "workflow", "init", "--kind", kind or "system", "--out", str(request.output_directory / "workflow.yaml")]
    return [
        {"id": "preflight", "status": "ready", "command": ["vladder", "can-optimize", source, "--symbol", symbol, "--out-dir", str(request.output_directory)]},
        {"id": "execute", "status": "blocked" if "<" in " ".join(executor) else "ready", "command": executor},
        {"id": "resume", "status": "ready", "command": ["vladder", "resume", "--out-dir", str(request.output_directory)]},
    ]


def _context_guidance(kind: str, first_unreachable: str | None) -> dict[str, Any]:
    rules = [
        "A generated candidate is not proof.",
        "A local proof does not establish owning-wrapper or external-protocol equivalence.",
        "Promotion requires representative physical evidence and application integration.",
    ]
    if kind in {"shader", "gpu"}:
        rules.append("Use device timestamps and an exact or declared-tolerance output oracle; host wall time alone is insufficient.")
    if first_unreachable == "application_integration":
        rules.append("Bind every declared output, status, state mutation, and external effect into the project oracle before promotion.")
    terms = {term: definition for term, definition in GLOSSARY.items() if term in {"semantic coverage", "candidate", "proof", "physical measurement", "application integration", "promotion", "external authority", "grammar coverage"}}
    return {"mandatory_rules": rules, "glossary": terms}


def build_plan(request: OptimizationRequest, registry: GrammarRegistry | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    project = request.project.resolve()
    source = request.source.resolve() if request.source else None
    source_text = source.read_text(errors="ignore") if source and source.exists() else ""
    region_text = _extract_function_text(source_text, request.symbol)
    classification = classify_region(source, request.symbol, project)
    if classification["kind"] == "cpp":
        classification["signature_projection"] = _cpp_signature_projection(region_text, request.symbol)
    contract = infer_contract(region_text, classification["language"], request.symbol)
    authorities = inventory_external_authorities(region_text)
    evidence = discover_project_evidence(project)
    evidence_override = request.output_directory.resolve() / "project-evidence.yaml"
    if evidence_override.exists():
        loaded_evidence = yaml.safe_load(evidence_override.read_text())
        if isinstance(loaded_evidence, dict) and loaded_evidence.get("schema_version") == PROJECT_EVIDENCE_SCHEMA:
            evidence["selected"] = dict(loaded_evidence.get("selected", evidence["selected"]))
            evidence["unresolved"] = list(loaded_evidence.get("unresolved", evidence["unresolved"]))
    contract_override = request.contract or (request.output_directory.resolve() / "contract-candidate.yaml")
    if contract_override.exists():
        loaded_contract = yaml.safe_load(contract_override.read_text())
        if isinstance(loaded_contract, dict):
            is_generated_scaffold = loaded_contract.get("schema_version") == "vladder-inferred-contract-v1"
            is_authoritative = request.contract is not None or loaded_contract.get("confirmed") is True
            if is_authoritative:
                supplied_facts = loaded_contract.get("contract")
                if not isinstance(supplied_facts, dict) and not is_generated_scaffold:
                    supplied_facts = {
                        key: value for key, value in loaded_contract.items()
                        if key not in {"schema_version", "confirmed", "unresolved_assumptions", "authority"}
                    }
                if isinstance(supplied_facts, dict):
                    contract["facts"].update(supplied_facts)
                contract["unresolved_assumptions"] = list(loaded_contract.get("unresolved_assumptions", []))
                contract["suggested_patch"] = []
                contract["authority"] = "explicit contract" if request.contract else "user-confirmed contract scaffold"
    compile_commands = request.compile_commands or (Path(evidence["compile_commands"]) if evidence.get("compile_commands") else None)
    coverage = grammar_coverage(region_text, registry)
    workload_share = _load_workload_share(request.profile, request.symbol)
    represent = representativeness(region_text, authorities, workload_share)
    forecast = forecast_workflow(classification, contract, authorities, evidence, coverage, compile_commands)
    decision = economic_decision(forecast, coverage, represent, workload_share, request.minimum_effect_percent)
    identity = {
        "version": __version__,
        "orchestrator_revision": ORCHESTRATOR_REVISION,
        "request": request.to_dict(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source and source.exists() else None,
        "contract_sha256": hashlib.sha256(request.contract.read_bytes()).hexdigest() if request.contract and request.contract.exists() else None,
        "workload_sha256": hashlib.sha256(request.workload.read_bytes()).hexdigest() if request.workload and request.workload.exists() else None,
        "grammar_sha256": registry.sha256,
    }
    plan_id = _hash(identity)
    steps = _plan_steps(classification["kind"], request, forecast["first_unreachable_state"])
    return {
        "schema_version": PLAN_SCHEMA,
        "plan_id": plan_id,
        "created_at": _now(),
        "vladder_version": __version__,
        "request": request.to_dict(),
        "classification": classification,
        "contract_candidate": contract,
        "external_authority_inventory": authorities,
        "cross_translation_unit": summarize_cross_tu_boundary(source, region_text, compile_commands, authorities),
        "project_evidence": evidence,
        "grammar_coverage": coverage,
        "representativeness": represent,
        "workload_share_percent": workload_share,
        "forecast": forecast,
        "steps": steps,
        "economic_decision": decision,
        "guidance": _context_guidance(classification["kind"], forecast["first_unreachable_state"]),
        "authority": "plan and forecast only; no legality, proof, performance, or promotion authority",
    }


def _stage_record(output_directory: Path, name: str, key_payload: Any, producer: Callable[[], dict[str, Any]], *, force: bool) -> tuple[dict[str, Any], str]:
    key = _hash({"stage": name, "inputs": key_payload, "vladder_version": __version__})
    path = output_directory / ".stages" / f"{name}-{key}.json"
    if path.exists() and not force:
        return json.loads(path.read_text()), "reused"
    value = producer()
    record = {
        "schema_version": "vladder-content-addressed-stage-v1",
        "stage": name,
        "stage_key": key,
        "created_at": _now(),
        "value": value,
    }
    _write_json(path, record)
    return record, "computed"


def _scaffold_project_evidence(plan: dict[str, Any], output_directory: Path) -> dict[str, str]:
    def write_yaml_once(path: Path, value: Any) -> None:
        if not path.exists():
            _write_yaml(path, value)

    def write_json_once(path: Path, value: Any) -> None:
        if not path.exists():
            _write_json(path, value)

    evidence_path = output_directory / "project-evidence.yaml"
    write_yaml_once(evidence_path, plan["project_evidence"])
    contract_path = output_directory / "contract-candidate.yaml"
    write_yaml_once(contract_path, {
        "schema_version": "vladder-inferred-contract-v1",
        "contract": plan["contract_candidate"]["facts"],
        "unresolved_assumptions": plan["contract_candidate"]["unresolved_assumptions"],
        "confirmed": False,
    })
    patch_path = output_directory / "contract-suggested-patch.json"
    write_json_once(patch_path, plan["contract_candidate"]["suggested_patch"])
    benchmark_path = output_directory / "paired-benchmark.yaml"
    write_yaml_once(benchmark_path, {
        "schema_version": "vladder-paired-benchmark-manifest-v2",
        "executable": "TODO_REQUIRED_same_executable",
        "baseline_args": ["baseline"],
        "candidate_args": ["candidate"],
        "metric_key": "metric",
        "observable_key": "observable_hash",
        "exact_observables": True,
        "direction": "lower",
        "minimum_processes": 10,
        "maximum_processes": 40,
        "repetitions_per_process": 3,
        "bootstrap_rounds": 2000,
        "stopping_rule": {"minimum_effect_percent": plan["request"]["minimum_effect_percent"], "target_ci_width_percent": 1.0},
        "candidate_order": "randomized_paired",
    })
    runner_path = output_directory / "physical-runner.yaml"
    authority_categories = {item["category"] for item in plan["external_authority_inventory"]}
    runner_backend = (
        "cuda" if plan["classification"]["kind"] == "gpu" and plan["request"]["source"] and str(plan["request"]["source"]).endswith(".cu") else
        "vulkan" if plan["classification"]["kind"] == "shader" else
        "network" if "network_io" in authority_categories else
        "local_command"
    )
    timing_domain = "device_timestamp" if runner_backend in {"cuda", "vulkan"} else "host_monotonic"
    write_yaml_once(runner_path, {
        "schema_version": RUNNER_SCHEMA,
        "backend": runner_backend,
        "timing_domain": timing_domain,
        "hardware_manifest": "TODO_REQUIRED",
        "workload_manifest": "TODO_REQUIRED",
        "command": ["TODO_REQUIRED"],
        "observable": {"field": "observable_hash", "contract": "exact"},
        "metrics": [{"field": "metric", "direction": "lower", "unit": "nanoseconds"}],
        "counters": (
            ["device_duration", "queue_wait", "transfer_bytes", "occupancy", "cache_transactions"]
            if runner_backend in {"cuda", "vulkan"} else
            ["cycles", "instructions", "cache_misses", "branch_misses"]
        ),
        "integrity": {"result_hash": "sha256", "signature": "optional_hmac_sha256"},
    })
    remote_path = output_directory / "remote-executor.yaml"
    write_yaml_once(remote_path, {
        "schema_version": "vladder-remote-executor-v1",
        "transport": "command_adapter",
        "executor": ["TODO_REQUIRED", "--request", "{request}", "--result", "{result}"],
        "request_manifest": "TODO_REQUIRED_remote-request.json",
        "immutable_inputs": ["hardware_manifest", "workload_manifest", "binary_hash", "candidate_hash"],
        "result_schema": REMOTE_RESULT_SCHEMA,
        "signature": {"algorithm": "hmac-sha256", "key_environment": "VLADDER_REMOTE_RESULT_KEY"},
        "promotion_authority": False,
    })
    adapter_path = output_directory / "application-adapter.yaml"
    signature = plan["classification"].get("signature_projection") or {}
    typed_adapter = _typed_cpp_adapter(plan, output_directory)
    write_yaml_once(adapter_path, {
        "schema_version": "vladder-generic-application-adapter-v1",
        "production_symbol": plan["classification"].get("symbol"),
        "inputs": signature.get("parameters") or "TODO_REQUIRED_bind_production_inputs",
        "baseline_entry": "TODO_REQUIRED",
        "candidate_entry": "TODO_REQUIRED",
        "observable_projection": "TODO_REQUIRED",
        "state_projection": "TODO_REQUIRED_if_stateful",
        "error_projection": "TODO_REQUIRED",
        "fallback": "production_baseline",
        "external_authorities": plan["external_authority_inventory"],
        "promotion_blocked": True,
        "next_command": ["vladder", "resume", "--out-dir", str(output_directory)],
    })
    return {
        "project_evidence": str(evidence_path),
        "contract": str(contract_path),
        "contract_patch": str(patch_path),
        "benchmark": str(benchmark_path),
        "physical_runner": str(runner_path),
        "remote_executor": str(remote_path),
        "application_adapter": str(adapter_path),
        **({"typed_application_adapter": str(typed_adapter)} if typed_adapter else {}),
    }


def terminal_status(summary: dict[str, Any]) -> str:
    states = summary.get("states", {})
    if states.get("production_promoted") and states.get("application_integrated"):
        return "PROMOTABLE"
    if states.get("production_promoted") and not states.get("application_integrated"):
        return "INTEGRATION_REQUIRED"
    if states.get("physically_benchmarked") and states.get("candidate_proved"):
        return "VERIFIED_REJECTION"
    if states.get("physically_benchmarked") and not states.get("application_integrated"):
        return "INTEGRATION_REQUIRED"
    if states.get("candidate_proved"):
        return "NO_BENCHMARK"
    if states.get("candidate_generated"):
        return "NO_PROOF"
    if states.get("meaningful_semantic_coverage"):
        return "NO_CANDIDATE"
    return "NO_COVERAGE"


def _proof_badge(summary: dict[str, Any]) -> dict[str, Any]:
    proof = str(summary.get("proof_class", "none")).lower()
    key = (
        "composed_local" if proof in {"bounded_c_region", "bounded_cpp_region", "composed_local"} else
        "alive2" if "alive" in proof or "llvm" in proof else
        "z3" if "z3" in proof or "state" in proof else
        "differential" if "differential" in proof else
        "structural" if proof not in {"", "none", "unclassified"} else
        "none"
    )
    return {**PROOF_BADGES[key], "proof_class": summary.get("proof_class"), "artifact": next((item["path"] for item in summary.get("decisive_artifacts", []) if "proof" in item["role"]), None)}


def _failure_records(summary: dict[str, Any], plan: dict[str, Any], scaffolds: dict[str, str]) -> list[dict[str, Any]]:
    failures = []
    status = terminal_status(summary)
    for blocker in summary.get("blockers", []):
        lowered = str(blocker).lower()
        code = "external_authority" if any(token in lowered for token in ("external", "protocol", "callback", "driver")) else "missing_contract" if any(token in lowered for token in ("contract", "observable", "alias", "state")) else "proof_failed" if "proof" in lowered else "missing_tool" if any(token in lowered for token in ("unavailable", "tool", "compiler")) else "integration_failed"
        failures.append({
            "code": code,
            "category": FAILURE_CATEGORIES[code],
            "message": str(blocker),
            "evidence_impact": status,
            "owner": "user_or_agent" if code in {"missing_contract", "integration_failed"} else "tool_or_adapter",
            "scaffold": scaffolds.get("application_adapter") if code in {"missing_contract", "external_authority", "integration_failed"} else scaffolds.get("contract"),
            "remediation": {"command": ["vladder", "resume", "--out-dir", plan["request"]["output_directory"]]},
        })
    if not failures and status != "PROMOTABLE":
        code = {
            "NO_COVERAGE": "missing_contract",
            "NO_CANDIDATE": "missing_contract",
            "NO_PROOF": "proof_failed",
            "NO_BENCHMARK": "integration_failed",
            "INTEGRATION_REQUIRED": "integration_failed",
            "VERIFIED_REJECTION": "benchmark_regression",
        }[status]
        failures.append({
            "code": code,
            "category": FAILURE_CATEGORIES[code],
            "message": str(summary.get("next_action") or status),
            "evidence_impact": status,
            "owner": "user_or_agent" if code in {"missing_contract", "integration_failed"} else "tool_or_adapter",
            "scaffold": scaffolds.get("application_adapter") if code in {"missing_contract", "integration_failed"} else scaffolds.get("benchmark"),
            "remediation": {"command": ["vladder", "resume", "--out-dir", plan["request"]["output_directory"]]},
        })
    return failures


def _concise_disposition(summary: dict[str, Any], plan: dict[str, Any], scaffolds: dict[str, str]) -> dict[str, Any]:
    states = summary.get("states", {})
    status = terminal_status(summary)
    proof = _proof_badge(summary)
    decision = economic_decision(
        plan["forecast"], plan["grammar_coverage"], plan["representativeness"],
        plan.get("workload_share_percent"), plan["request"]["minimum_effect_percent"], summary=summary,
    )
    next_command = ["vladder", "resume", "--out-dir", plan["request"]["output_directory"]]
    if status == "PROMOTABLE":
        next_command = ["vladder", "verify-application", "--help"]
    return {
        "schema_version": "vladder-agent-disposition-v1",
        "terminal_status": status,
        "facts": {
            "coverage": "PASS" if states.get("meaningful_semantic_coverage") else "MISSING",
            "candidate": "GENERATED" if states.get("candidate_generated") else "NONE",
            "proof": proof["badge"],
            "measurement": "MEASURED" if states.get("physically_benchmarked") else "NOT_RUN",
            "integration": "PASS" if states.get("application_integrated") else "NOT_ESTABLISHED",
        },
        "proof_badge": proof,
        "promotion_permitted": bool(summary.get("promotion_permitted")),
        "economic_decision": decision,
        "grammar_coverage": {
            "classification": plan["grammar_coverage"]["coverage_classification"],
            "negative_result_authority": plan["grammar_coverage"]["negative_result_authority"],
        },
        "representativeness": plan["representativeness"],
        "failures": _failure_records(summary, plan, scaffolds),
        "next_action": {
            "description": summary.get("next_action"),
            "command": next_command,
            "required_scaffold": scaffolds.get("application_adapter") if status in {"NO_COVERAGE", "INTEGRATION_REQUIRED"} else None,
        },
        "decisive_artifacts": summary.get("decisive_artifacts", [])[:5],
        "full_summary": str(Path(plan["request"]["output_directory"]) / "promotion-summary.json"),
    }


def write_plan(request: OptimizationRequest, *, emit_progress: bool = True) -> dict[str, Any]:
    output = request.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    progress = ProgressWriter(output, emit=emit_progress)
    progress.write("DISCOVERY", 5, "classifying region and discovering project evidence", estimated_remaining_seconds=10)
    request_record = request.to_dict()
    _write_json(output / "request.json", {"schema_version": "vladder-optimization-request-v1", **request_record})
    stage_inputs = {
        "request": request_record,
        "orchestrator_revision": ORCHESTRATOR_REVISION,
        "project": _path_identity(request.project),
        "source": _path_identity(request.source),
        "compile_commands": _path_identity(request.compile_commands),
        "contract": _path_identity(request.contract),
        "workload": _path_identity(request.workload),
        "profile": _path_identity(request.profile),
        "project_evidence_scaffold": _scaffold_override_identity(output / "project-evidence.yaml", "project_evidence"),
        "contract_scaffold": _scaffold_override_identity(output / "contract-candidate.yaml", "contract"),
        "application_adapter_scaffold": _scaffold_override_identity(output / "application-adapter.yaml", "application_adapter"),
        "physical_runner_scaffold": _scaffold_override_identity(output / "physical-runner.yaml", "physical_runner"),
    }
    record, origin = _stage_record(output, "plan", stage_inputs, lambda: build_plan(request), force=request.force)
    plan = record["value"]
    plan["cache"] = {"plan": origin, "stage_key": record["stage_key"]}
    progress.write("FEASIBILITY", 35, f"forecast complete; first unreachable={plan['forecast']['first_unreachable_state'] or 'none'}")
    scaffolds = _scaffold_project_evidence(plan, output)
    plan["scaffolds"] = scaffolds
    _write_json(output / "optimization-plan.json", plan)
    progress.write("PLAN", 45, f"authoritative plan {plan['plan_id'][:12]} ready", artifact=output / "optimization-plan.json")
    return plan


def _workflow_manifest(plan: dict[str, Any], output: Path) -> Path:
    request = plan["request"]
    kind = plan["classification"]["kind"]
    source = request.get("source")
    symbol = request.get("symbol")
    action = "optimize"
    if kind == "cpp" and plan["forecast"]["first_unreachable_state"] in {"physical_measurement", "application_integration"}:
        action = "isolate"
    region: dict[str, Any] = {"kind": kind, "action": action}
    if kind in {"c", "cpp"}:
        region.update({"source": source, "function": symbol})
        if kind == "cpp":
            region["compile_commands"] = request.get("compile_commands") or plan["project_evidence"].get("compile_commands") or "build/compile_commands.json"
            region["symbol"] = None
            region["command_index"] = None
    elif kind == "rust":
        region.update({"source": source, "function": symbol, "manifest": str(Path(request["project"]) / "Cargo.toml"), "profile": "release", "features": [], "proof_bound": 32})
    elif kind == "zig":
        region.update({"source": source, "function": symbol, "build_root": request["project"], "optimize_mode": "ReleaseFast", "target": "native", "proof_bound": 32})
    elif kind == "julia":
        region.update({"source": source, "function": symbol, "project": request["project"], "module": "Main", "signature": "TODO_REQUIRED", "cpu_target": "native", "proof_bound": 32})
        region["action"] = "inspect"
    elif kind == "shader":
        region.update({"source": source, "target_env": "vulkan1.2", "runner_manifest": str(output / "physical-runner.yaml")})
        region["action"] = "synthesize"
    manifest = {
        "schema_version": "vladder-agent-workflow-v1",
        "name": f"orchestrated-{symbol or kind}",
        "region": region,
        "contract": {"identity": _hash(plan["contract_candidate"]), "exact": True},
        "attribution": {"profile_report": request.get("profile"), "regional_share_percent": plan.get("workload_share_percent")},
        "workload": {"identity": request.get("workload") or "unbound", "held_out": False},
        "promotion": {"minimum_effect_percent": request["minimum_effect_percent"], "requires_composed_confirmation": True},
        "retained_candidate_identity": None,
    }
    path = output / "workflow.yaml"
    _write_yaml(path, manifest)
    return path


def execute_plan(
    request: OptimizationRequest,
    plan: dict[str, Any],
    *,
    c_executor: Callable[[], int] | None = None,
    emit_progress: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = request.output_directory.resolve()
    progress = ProgressWriter(output, emit=emit_progress)
    progress.write("EXECUTE", 50, f"delegating to {plan['classification']['kind']} workflow", estimated_remaining_seconds=plan["forecast"]["estimated_runtime_seconds"]["high"])
    kind = plan["classification"]["kind"]
    if plan["forecast"]["first_unreachable_state"] == "semantic_coverage":
        report = {
            "schema_version": f"vladder-{kind or 'unknown'}-preflight-v1",
            "status": "adapter_required",
            "language": "c++" if kind == "cpp" else kind,
            "closure": {
                "disposition": "preflight_blocked",
                "capabilities": {
                    "semantic_capture": {"actual": False},
                    "candidate_generation": {"actual": False},
                    "local_proof": {"actual": False},
                    "benchmark": {"actual": False},
                },
            },
            "adapters": [{
                "kind": item["name"],
                "reason": f"required dependency is unavailable: {item['name']}",
                "required_boundary": item.get("remediation") or "complete generated scaffold",
            } for item in plan["forecast"]["dependencies"] if item["required"] and not item["available"]],
            "claim_boundary": "early feasibility only; no semantic extraction or proof was attempted",
        }
        report_path = output / "preflight-blocker.json"
        _write_json(report_path, report)
        summary = summarize_report(report_path, output / "promotion-summary.json")
    elif kind == "unknown":
        report = {
            "schema_version": "vladder-unroutable-region-v1",
            "status": "adapter_required",
            "automatic_region": {"supported": False},
            "blockers": ["source language or region kind could not be classified"],
        }
        report_path = output / "unroutable-report.json"
        _write_json(report_path, report)
        summary = summarize_report(report_path, output / "promotion-summary.json")
    elif kind == "c" and c_executor is not None:
        rc = c_executor()
        report_path = output / "perf.json"
        if not report_path.exists():
            raise RuntimeError(f"bounded C executor returned {rc} without perf.json")
        summary = summarize_report(report_path, output / "promotion-summary.json")
    else:
        workflow = _workflow_manifest(plan, output)
        summary = run_agent_workflow(workflow, output / "workflow-out", force=request.force)
        _write_json(output / "promotion-summary.json", summary)
    progress.write("DISPOSITION", 92, f"terminal evidence state={terminal_status(summary)}", artifact=output / "promotion-summary.json")
    disposition = _concise_disposition(summary, plan, plan["scaffolds"])
    _write_json(output / "disposition.json", disposition)
    progress.write("COMPLETE", 100, f"{disposition['terminal_status']} recommendation={disposition['economic_decision']['recommendation']}", artifact=output / "disposition.json", estimated_remaining_seconds=0)
    return summary, disposition


def run_optimization(
    request: OptimizationRequest,
    *,
    c_executor: Callable[[], int] | None = None,
    emit_progress: bool = True,
) -> dict[str, Any]:
    plan = write_plan(request, emit_progress=emit_progress)
    if request.plan_only:
        return {"plan": plan, "summary": None, "disposition": None}
    summary, disposition = execute_plan(request, plan, c_executor=c_executor, emit_progress=emit_progress)
    return {"plan": plan, "summary": summary, "disposition": disposition}


def resume_optimization(output_directory: Path, *, force: bool = False, emit_progress: bool = True, c_executor: Callable[[], int] | None = None) -> dict[str, Any]:
    request_path = output_directory.resolve() / "request.json"
    if not request_path.exists():
        raise ValueError(f"no resumable request exists at {request_path}")
    raw = json.loads(request_path.read_text())
    request = OptimizationRequest(
        project=Path(raw["project"]),
        source=Path(raw["source"]) if raw.get("source") else None,
        symbol=raw.get("symbol"),
        compile_commands=Path(raw["compile_commands"]) if raw.get("compile_commands") else None,
        contract=Path(raw["contract"]) if raw.get("contract") else None,
        workload=Path(raw["workload"]) if raw.get("workload") else None,
        profile=Path(raw["profile"]) if raw.get("profile") else None,
        output_directory=output_directory,
        minimum_effect_percent=float(raw.get("minimum_effect_percent", 1.0)),
        plan_only=False,
        force=force,
    )
    return run_optimization(request, c_executor=c_executor, emit_progress=emit_progress)


def inventory_repository(project: Path, *, max_regions: int = 50) -> list[dict[str, Any]]:
    project = project.resolve()
    regions: list[dict[str, Any]] = []
    ignored = {".git", "build", "dist", "node_modules", ".venv", "venv", "target", ".cache"}
    for source in sorted(project.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in LANGUAGE_EXTENSIONS:
            continue
        if any(part in ignored for part in source.parts):
            continue
        text = source.read_text(errors="ignore")
        language = LANGUAGE_EXTENSIONS[source.suffix.lower()]
        if language in {"shader", "gpu"}:
            symbols = [source.stem]
        else:
            symbols = re.findall(r"\b([A-Za-z_]\w*(?:::\w+)*)\s*\([^;{}]{0,300}\)\s*(?:const\s*)?(?:noexcept\s*)?\{", text)
        for symbol in symbols[:20]:
            region_text = _extract_function_text(text, symbol)
            score = (
                len(re.findall(r"\b(for|while)\b", region_text)) * 3
                + len(re.findall(r"\b(if|switch)\b", region_text))
                + len(region_text) / 1000.0
                + len(inventory_external_authorities(region_text)) * 2
            )
            regions.append({
                "id": _hash({"source": str(source.relative_to(project)), "symbol": symbol})[:16],
                "source": str(source),
                "symbol": symbol,
                "language": language,
                "priority_score": round(score, 3),
            })
    regions.sort(key=lambda item: (-item["priority_score"], item["source"], item["symbol"]))
    return regions[:max_regions]


def run_portfolio(
    project: Path,
    output_directory: Path,
    *,
    max_regions: int = 20,
    execute: bool = False,
    compile_commands: Path | None = None,
    workers: int = 4,
) -> dict[str, Any]:
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    inventory = inventory_repository(project, max_regions=max_regions)
    workers = max(1, min(workers, max(1, len(inventory))))

    def prepare(region: dict[str, Any]) -> tuple[dict[str, Any], OptimizationRequest, dict[str, Any], str]:
        request = OptimizationRequest(
            project=project,
            source=Path(region["source"]),
            symbol=region["symbol"],
            compile_commands=compile_commands,
            contract=None,
            workload=None,
            profile=None,
            output_directory=output / "regions" / region["id"],
            plan_only=not execute,
        )
        plan = write_plan(request, emit_progress=False)
        canonical_facts = {
            key: value for key, value in plan["contract_candidate"]["facts"].items()
            if key != "symbol"
        }
        semantic_root = _hash({
            "classification": plan["classification"]["kind"],
            "contract_facts": canonical_facts,
            "families": [item["family"] for item in plan["grammar_coverage"]["recognized_families"]],
        })
        return region, request, plan, semantic_root

    with ThreadPoolExecutor(max_workers=workers) as executor:
        prepared = list(executor.map(prepare, inventory))

    results = []
    seen_roots: dict[str, str] = {}
    unique_jobs: list[tuple[OptimizationRequest, str]] = []
    for region, request, plan, semantic_root in prepared:
        duplicate_of = seen_roots.get(semantic_root)
        if duplicate_of is None:
            seen_roots[semantic_root] = region["id"]
            if execute:
                unique_jobs.append((request, region["id"]))
        results.append({
            **region,
            "semantic_root": semantic_root,
            "duplicate_of": duplicate_of,
            "forecast": plan["forecast"],
            "economic_decision": plan["economic_decision"],
            "terminal_status": None,
            "plan": str(request.output_directory / "optimization-plan.json"),
        })

    if unique_jobs:
        def execute_unique(job: tuple[OptimizationRequest, str]) -> tuple[str, str | None]:
            request, region_id = job
            executed = run_optimization(request, emit_progress=False)
            disposition = executed.get("disposition") or {}
            return region_id, disposition.get("terminal_status")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            terminal_by_region = dict(executor.map(execute_unique, unique_jobs))
        for result in results:
            if result["duplicate_of"] is None:
                result["terminal_status"] = terminal_by_region.get(result["id"])
    report = {
        "schema_version": CAMPAIGN_SCHEMA,
        "project": str(project.resolve()),
        "region_count": len(results),
        "unique_semantic_roots": len(seen_roots),
        "duplicate_count": sum(item["duplicate_of"] is not None for item in results),
        "execution_requested": execute,
        "workers": workers,
        "regions": results,
        "summary": {
            "continue": sum(item["economic_decision"]["recommendation"] == "CONTINUE" for item in results),
            "stop": sum(item["economic_decision"]["recommendation"] == "STOP" for item in results),
            "escalate": sum(item["economic_decision"]["recommendation"] == "ESCALATE" for item in results),
        },
    }
    _write_json(output / "portfolio-summary.json", report)
    return report


def sign_remote_result(result: dict[str, Any], key: str) -> dict[str, Any]:
    payload = {key_name: value for key_name, value in result.items() if key_name != "signature"}
    signature = hmac.new(key.encode(), json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
    return {**payload, "signature": {"algorithm": "hmac-sha256", "digest": signature}}


def verify_remote_result(result: dict[str, Any], request_manifest: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    errors = []
    if result.get("schema_version") != REMOTE_RESULT_SCHEMA:
        errors.append("unexpected remote result schema")
    for field in ("hardware_manifest_sha256", "workload_manifest_sha256", "binary_sha256", "candidate_sha256"):
        expected = request_manifest.get(field)
        if expected and result.get(field) != expected:
            errors.append(f"{field} does not match immutable request")
    if key:
        signature = result.get("signature", {}).get("digest") if isinstance(result.get("signature"), dict) else None
        expected = sign_remote_result(result, key)["signature"]["digest"]
        if not signature or not hmac.compare_digest(str(signature), str(expected)):
            errors.append("remote result signature is invalid")
    return {
        "schema_version": "vladder-remote-result-verification-v1",
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "promotion_authority": False,
        "claim_boundary": "integrity and identity only; semantic parity and physical promotion remain separate gates",
    }


def execute_remote_adapter(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("remote executor manifest must be a mapping")
    command_template = raw.get("executor")
    if not isinstance(command_template, list) or not command_template:
        raise ValueError("remote executor requires an argv-form executor list")
    request_path = Path(str(raw.get("request_manifest", "")))
    if not request_path.is_absolute():
        request_path = (manifest_path.parent / request_path).resolve()
    if not request_path.exists():
        raise ValueError(f"remote request manifest does not exist: {request_path}")
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    result_path = output_directory / "remote-result.json"
    command = [
        str(item).replace("{request}", str(request_path)).replace("{result}", str(result_path))
        for item in command_template
    ]
    completed = subprocess.run(
        command,
        cwd=str(manifest_path.parent),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=float(raw.get("timeout_seconds", 3600.0)),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"remote executor failed ({completed.returncode}): {completed.stderr[-3000:]}")
    if not result_path.exists():
        raise RuntimeError("remote executor did not materialize the declared result bundle")
    result = json.loads(result_path.read_text())
    request = json.loads(request_path.read_text()) if request_path.suffix == ".json" else yaml.safe_load(request_path.read_text())
    if not isinstance(request, dict) or not isinstance(result, dict):
        raise ValueError("remote request and result must be mappings")
    key_name = str(raw.get("signature", {}).get("key_environment", "VLADDER_REMOTE_RESULT_KEY")) if isinstance(raw.get("signature"), dict) else "VLADDER_REMOTE_RESULT_KEY"
    verification = verify_remote_result(result, request, os.environ.get(key_name))
    report = {
        "schema_version": "vladder-remote-execution-v1",
        "status": verification["status"],
        "command": command,
        "request_manifest": str(request_path),
        "result": str(result_path),
        "stdout_tail": completed.stdout[-2000:],
        "verification": verification,
        "promotion_authority": False,
    }
    _write_json(output_directory / "remote-execution.json", report)
    return report


def format_terminal(disposition: dict[str, Any]) -> str:
    facts = disposition["facts"]
    lines = [
        f"vLadder disposition: {disposition['terminal_status']}",
        "  " + " | ".join(f"{name}={value}" for name, value in facts.items()),
        f"  decision={disposition['economic_decision']['recommendation']}: {disposition['economic_decision']['reason']}",
    ]
    command = disposition.get("next_action", {}).get("command")
    if command:
        lines.append("  next=" + shlex.join(str(item) for item in command))
    return "\n".join(lines)
