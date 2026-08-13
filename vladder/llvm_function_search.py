from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from importlib.resources import files
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from .deep_benchmark import _hot_assembly_identity
from .language_adapter import canonical_hash
from .toolchain import alive2_refinement_check, discover_toolchain


LLVM_FUNCTION_GRAMMAR_VERSION = "llvm-function-v1"


@dataclass(frozen=True)
class LLVMFunctionPipeline:
    id: str
    passes: str
    class_name: str


def load_llvm_function_pipelines() -> tuple[LLVMFunctionPipeline, ...]:
    resource = files("vladder").joinpath("grammars/llvm-function-v1/grammar.json")
    raw = json.loads(resource.read_text())
    if raw.get("schema_version") != "vladder-llvm-function-grammar-v1":
        raise ValueError("unsupported LLVM function grammar schema")
    rows = tuple(
        LLVMFunctionPipeline(str(item["id"]), str(item["passes"]), str(item["class"]))
        for item in raw.get("pipelines", ())
    )
    if not rows or rows[0].id != "baseline" or len({item.id for item in rows}) != len(rows):
        raise ValueError("LLVM function grammar requires one leading baseline and unique pipeline IDs")
    return rows


def capture_llvm_function(
    report: Mapping[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    """Extract one selected function with all required module-level declarations."""
    output_directory.mkdir(parents=True, exist_ok=True)
    selection = report.get("selection") if isinstance(report.get("selection"), Mapping) else {}
    production = report.get("production_ir") if isinstance(report.get("production_ir"), Mapping) else {}
    requested_symbol = str(selection.get("symbol") or "")
    resolved_symbols = production.get("resolved_symbols", {}) if isinstance(production, Mapping) else {}
    symbol = str(resolved_symbols.get("production") or requested_symbol)
    module = Path(str(production.get("raw_ir") or ""))
    extractor = shutil.which("llvm-extract-20") or shutil.which("llvm-extract")
    if not requested_symbol:
        return {"status": "blocked", "reason": "selected compiled symbol is absent"}
    if not module.is_file():
        return {"status": "blocked", "reason": "production LLVM module is absent", "symbol": symbol}
    if not extractor:
        return {"status": "blocked", "reason": "llvm-extract is unavailable", "symbol": symbol}
    baseline = output_directory / "selected-function.ll"
    completed = subprocess.run(
        [extractor, f"--func={symbol}", "-S", str(module), "-o", str(baseline)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
    )
    if completed.returncode or not baseline.is_file():
        return {
            "status": "blocked",
            "reason": "llvm-extract could not isolate the selected function",
            "symbol": symbol,
            "stderr": completed.stderr[-4000:],
        }
    pipelines = load_llvm_function_pipelines()
    payload = {
        "schema_version": "vladder-llvm-function-capture-v1",
        "status": "pass",
        "grammar_version": LLVM_FUNCTION_GRAMMAR_VERSION,
        "symbol": symbol,
        "requested_ast_symbol": requested_symbol,
        "symbol_resolution": list(production.get("alias_chains", {}).get("production", [requested_symbol])),
        "source_function": selection.get("name"),
        "source_sha256": report.get("source_sha256"),
        "compile_command_sha256": report.get("compile_command", {}).get("command_sha256"),
        "baseline_module": str(baseline),
        "baseline_module_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
        "pipelines": [item.id for item in pipelines],
        "claim_boundary": (
            "same-signature selected-function LLVM refinement; external calls remain declarations "
            "and no owning protocol rewrite is inferred"
        ),
    }
    payload["capture_hash"] = canonical_hash(payload)
    artifact = output_directory / "llvm-function-capture.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {**payload, "artifact": str(artifact)}


def evaluate_llvm_function_pipeline(
    capture: Mapping[str, Any],
    pipeline_id: str,
    output_directory: Path,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    pipelines = {item.id: item for item in load_llvm_function_pipelines()}
    if pipeline_id not in pipelines:
        raise ValueError(f"unknown LLVM function pipeline: {pipeline_id}")
    pipeline = pipelines[pipeline_id]
    baseline = Path(str(capture["baseline_module"]))
    candidate = output_directory / "candidate.ll"
    opt = shutil.which("opt-20") or shutil.which("opt")
    if pipeline.id == "baseline":
        shutil.copy2(baseline, candidate)
        transform = {"status": "PASS", "command": ["identity-copy"]}
    elif not opt:
        transform = {"status": "FAIL", "reason": "opt is unavailable"}
    else:
        command = [opt, "-S", f"-passes={pipeline.passes}", str(baseline), "-o", str(candidate)]
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=240,
        )
        transform = {
            "status": "PASS" if completed.returncode == 0 and candidate.is_file() else "FAIL",
            "command": command,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-4000:],
        }
    symbol = str(capture["symbol"])
    if transform["status"] == "PASS":
        proof = alive2_refinement_check(
            discover_toolchain(),
            baseline,
            candidate,
            output_directory / "proof",
            pipeline.id,
            function=symbol,
            timeout=90,
        )
        compile_result = _compile_module(candidate, symbol, output_directory / "build")
    else:
        proof = {"status": "incorrect", "reason": "candidate LLVM module was not generated"}
        compile_result = {"status": "FAIL", "reason": transform.get("reason") or transform.get("stderr")}
    proof_status = {
        "correct": "PASS",
        "incorrect": "FAIL",
    }.get(str(proof.get("status")), "UNAVAILABLE")
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.is_file() else None
    return {
        "candidate_id": canonical_hash({
            "capture": capture.get("capture_hash"),
            "pipeline": pipeline.id,
            "candidate": candidate_hash,
        }),
        "realization": pipeline.id,
        "parameters": {
            "pipeline": pipeline.id,
            "pipeline_class": pipeline.class_name,
            "passes": pipeline.passes,
        },
        "source_sha256": None,
        "llvm_ir_sha256": candidate_hash,
        "proof_status": proof_status,
        "proof_class": "alive2-selected-function-two-module-refinement-v1",
        "compile_status": str(compile_result.get("status", "FAIL")),
        "assembly_identity": compile_result.get("assembly_identity"),
        "evaluation_resolved": (
            proof_status in {"PASS", "FAIL"}
            and compile_result.get("status") in {"PASS", "FAIL"}
        ),
        "transform": transform,
        "proof": proof,
        "compile": compile_result,
        "artifacts": {
            "llvm_ir": str(candidate) if candidate.is_file() else None,
            "proof": proof.get("log"),
            "assembly": compile_result.get("assembly"),
        },
    }


def _compile_module(module: Path, symbol: str, output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    llc = shutil.which("llc-20") or shutil.which("llc")
    if not llc:
        return {"status": "FAIL", "reason": "llc is unavailable"}
    assembly = output_directory / "candidate.s"
    command = [llc, "-O3", "-filetype=asm", "-mcpu=native", str(module), "-o", str(assembly)]
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
    )
    if completed.returncode or not assembly.is_file():
        return {
            "status": "FAIL",
            "command": command,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-4000:],
        }
    identity = _hot_assembly_identity(assembly, symbol)
    return {
        "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
        "command": command,
        "assembly": str(assembly),
        "assembly_identity": identity.get("normalized_sha256"),
        "identity": identity,
        "stderr": completed.stderr[-2000:],
    }
