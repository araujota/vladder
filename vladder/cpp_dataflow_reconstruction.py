from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from .dataflow_ir import BoundedDataflowContract
from .dataflow_lowering import DataflowCandidate
from .selected_build_search import _compile_translation_unit


CPP_DATAFLOW_RECONSTRUCTION_VERSION = "bounded-cpp-dataflow-reconstruction-v1"


def exact_dataflow_reconstruction_applicable(
    source_region: str,
    function: str,
    contract: BoundedDataflowContract,
    compiler_report: Mapping[str, Any],
) -> tuple[bool, str]:
    if contract.family not in {"predicate-stable-compaction", "fixed-width-codec"}:
        return False, "this bounded dataflow family has no exact owning C++ composer"
    if "::" in function:
        return False, "member and qualified owning wrappers require an object-state adapter"
    selection = compiler_report.get("selection", {})
    source_range = selection.get("source_range")
    if not isinstance(source_range, list) or len(source_range) != 2:
        return False, "compiler-selected complete source range is unavailable"
    header = source_region.split("{", 1)[0]
    leaf = function.rsplit("::", 1)[-1]
    signature = re.search(rf"(?s)(.*?)\b{re.escape(leaf)}\s*\((.*)\)\s*noexcept\s*$", header.strip())
    if not signature:
        return False, "selected function is not an exact nonthrowing free-function boundary"
    result = _normalize_type(signature.group(1).split()[-1])
    parameters = _split_parameters(signature.group(2))
    if contract.family == "predicate-stable-compaction":
        if result != "size_t":
            return False, "result is not the canonical exact output extent/status type"
        expected = (
            "uint32_t*",
            f"uint{contract.element_bits}_t*",
            "size_t",
            f"const uint{contract.element_bits}_t*",
            f"const uint{contract.element_bits}_t*",
            "size_t",
        )
    else:
        if result != "uint64_t":
            return False, "codec result is not the canonical packed 64-bit word"
        expected = ("uint16_t", "uint16_t", "uint32_t")
    actual = tuple(_parameter_type(item) for item in parameters)
    if actual != expected:
        return False, f"selected ABI {actual!r} does not match canonical bounded compaction ABI {expected!r}"
    if not compiler_report.get("typed_abi", {}).get("modeled"):
        return False, "compiler ABI is not fully modeled"
    effects = compiler_report.get("compiled_effects", {})
    if effects.get("external_calls") or effects.get("indirect_calls") or effects.get("unwind_operations"):
        return False, "selected function contains an unclosed call or exception boundary"
    return True, f"compiler-selected ABI exactly matches the bounded {contract.family} proof unit"


def reconstruct_exact_dataflow_translation_unit(
    candidate: DataflowCandidate,
    contract: BoundedDataflowContract,
    compiler_report: Mapping[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    original = Path(str(compiler_report["source"])).resolve()
    original_text = original.read_text()
    begin, end = (int(item) for item in compiler_report["selection"]["source_range"])
    if not (0 <= begin < end <= len(original_text)):
        raise ValueError("compiler-selected source range is outside the translation unit")
    selected = original_text[begin:end]
    function = str(compiler_report.get("function") or "")
    applicable, reason = exact_dataflow_reconstruction_applicable(
        selected, function, contract, compiler_report,
    )
    if not applicable:
        return {"status": "NOT_APPLICABLE", "reason": reason, "replacement_ready": False}

    body = _strip_generated_includes(candidate.source)
    public_pattern = re.compile(
        rf'extern "C"\s+[^\n{{;]+\s+{re.escape(candidate.function)}\s*\('
    )
    if len(public_pattern.findall(body)) != 1:
        raise ValueError("generated candidate does not expose one canonical public entry")
    leaf = function.rsplit("::", 1)[-1]
    body = body.replace(candidate.function, f"{leaf}_vladder_impl")
    body = re.sub(
        rf'extern "C"\s+([^\n{{;]+)\s+{re.escape(leaf)}_vladder_impl\s*\(',
        rf"\1 {leaf}(",
        body,
        count=1,
    )
    includes = "".join(
        f"#include <{header}>\n"
        for header in ("algorithm", "array", "bit", "cstdint", "cstring", "immintrin.h", "limits")
    )
    generated = includes + original_text[:begin] + body + original_text[end:]
    output_directory.mkdir(parents=True, exist_ok=True)
    source_path = output_directory / original.name
    source_path.write_text(generated)
    compiled = _compile_translation_unit(compiler_report, original, source_path, output_directory)
    return {
        "status": "PASS" if compiled.get("status") == "PASS" else "FAIL",
        "replacement_ready": compiled.get("status") == "PASS",
        "version": CPP_DATAFLOW_RECONSTRUCTION_VERSION,
        "reason": reason,
        "source": str(source_path),
        "source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "selected_source_sha256": hashlib.sha256(selected.encode()).hexdigest(),
        "compile": compiled,
        "assembly_identity": compiled.get("assembly_identity"),
        "proof_binding": {
            "class": "exact-abi-source-composition",
            "semantic_candidate_sha256": candidate.source_sha256,
            "compiler_selection_symbol": compiler_report.get("selection", {}).get("symbol"),
            "claim": (
                "the complete selected free-function definition has the exact proof-unit ABI; "
                "the proved generated body replaces that definition and compiles under its production command"
            ),
        },
    }


def _strip_generated_includes(source: str) -> str:
    lines = source.splitlines(keepends=True)
    while lines and (lines[0].startswith("#include ") or not lines[0].strip()):
        lines.pop(0)
    return "".join(lines)


def _split_parameters(parameters: str) -> tuple[str, ...]:
    result: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(parameters):
        if char in "<([{":
            depth += 1
        elif char in ">)]}":
            depth -= 1
        elif char == "," and depth == 0:
            result.append(parameters[start:index].strip())
            start = index + 1
    tail = parameters[start:].strip()
    if tail:
        result.append(tail)
    return tuple(result)


def _parameter_type(parameter: str) -> str:
    value = re.sub(r"\b(?:__restrict__|__restrict|restrict)\b", "", parameter)
    value = re.sub(r"\s+[A-Za-z_]\w*\s*$", "", value.strip())
    return _normalize_type(value)


def _normalize_type(value: str) -> str:
    value = value.replace("std::", "")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*\*\s*", "*", value)
    value = value.replace("uint const", "const uint")
    return value
