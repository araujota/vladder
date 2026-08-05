from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse
from typing import Any

from .candidates import Candidate, detect_affine, detect_clamp, detect_div_power2
from .extractor import extract_function
from .flow import FlowGraph, build_flow_graph
from .proofs import proof_to_dict, prove_candidate
from .toolchain import Toolchain, run


@dataclass(frozen=True)
class LLMAttempt:
    round: int
    status: str
    diagnostics: list[str]
    model: str
    response_chars: int = 0


@dataclass(frozen=True)
class LLMLiftResult:
    status: str
    candidate: Candidate | None
    attempts: list[LLMAttempt]
    provider: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("candidate")
        return data


FORBIDDEN = re.compile(
    r"\b(?:malloc|calloc|realloc|free|printf|fprintf|fopen|read|write|open|close|system|fork|exec|pthread_|std::|asm|__asm__)\b"
)


def zero_trust_llm_lift(fn_source: str, graph: FlowGraph, tc: Toolchain, work_dir: Path, rounds: int = 3) -> LLMLiftResult:
    key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-reasoner")
    provider = {"name": "deepseek-openai-compatible", "base_url": base_url, "model": model, "credential_present": bool(key)}
    if not key:
        return LLMLiftResult("unavailable", None, [LLMAttempt(0, "unavailable", ["DEEPSEEK_API_KEY is not set in the optimizer process"], model)], provider)
    work_dir.mkdir(parents=True, exist_ok=True)
    semantic_path = work_dir.parent / "analysis" / "semantic_model.smt2"
    semantic_smt = semantic_path.read_text(errors="replace") if semantic_path.exists() else "; semantic SMT artifact unavailable"
    feedback = "No prior attempt."
    attempts: list[LLMAttempt] = []
    for round_no in range(1, max(1, rounds) + 1):
        prompt = _prompt(fn_source, graph, semantic_smt, feedback)
        try:
            response = _chat(base_url, key, model, prompt)
        except Exception as exc:
            attempts.append(LLMAttempt(round_no, "provider_error", [str(exc)[:1000]], model))
            feedback = f"Provider error: {str(exc)[:500]}"
            continue
        source, decode_error = _decode_response(response)
        if decode_error:
            diagnostics = [decode_error]
        else:
            diagnostics = _validate_source(source, graph, tc, work_dir / f"round-{round_no}")
        if diagnostics:
            attempts.append(LLMAttempt(round_no, "rejected", diagnostics, model, len(response)))
            feedback = "\n".join(f"- {item}" for item in diagnostics)
            continue
        proof = _proof_name(graph.canonical)
        candidate = Candidate("llm_zero_trust_lift", source, tags=("llm-proposed", "zero-trust", "graph-validated"), proof=proof)
        proof_result = prove_candidate(extract_function(fn_source, "transform"), candidate)
        if proof_result.status != "PROVED":
            diagnostics = ["SMT obligation did not prove", json.dumps(proof_to_dict(proof_result), sort_keys=True)]
            attempts.append(LLMAttempt(round_no, "rejected", diagnostics, model, len(response)))
            feedback = "\n".join(diagnostics)
            continue
        attempts.append(LLMAttempt(round_no, "admitted_to_runtime_verification", [], model, len(response)))
        return LLMLiftResult("admitted", candidate, attempts, provider)
    return LLMLiftResult("exhausted", None, attempts, provider)


def _prompt(fn_source: str, graph: FlowGraph, semantic_smt: str, feedback: str) -> str:
    semantic = {
        "family": graph.family,
        "canonical": graph.canonical,
        "invariants": graph.invariants,
        "parameters": {k: v for k, v in graph.source_pattern.items() if k not in {"family", "canonical", "ir_evidence", "ir_constants"}},
        "nodes": [{"id": n.id, "opcode": n.opcode, "type": n.type, "attrs": n.attrs} for n in graph.nodes],
        "edges": [asdict(e) for e in graph.edges],
    }
    return (
        "You are the untrusted C reconstruction proposer in a proof-carrying superoptimizer. "
        "Reconstruct exactly one C99 function named transform_candidate with signature "
        "void transform_candidate(float *dst, const float *src, size_t n). Preserve bit-exact IEEE-754 behavior, NaN behavior, signed zero, memory access order, and bounds. "
        "Do not emit includes, markdown, explanations, helper functions, calls, allocation, I/O, threads, system calls, inline assembly, or undefined behavior. "
        "Return strict JSON with one key, c_source. The verifier distrusts every token and will return counterexamples or diagnostics.\n\n"
        f"ORIGINAL:\n{fn_source}\n\nSEMANTIC_GRAPH:\n{json.dumps(semantic, sort_keys=True)}\n\nBOUNDED_SMT_SEMANTICS:\n{semantic_smt}\n\nPREVIOUS_VERIFIER_FEEDBACK:\n{feedback}"
    )


def _chat(base_url: str, key: str, model: str, prompt: str) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("LLM endpoint must use HTTPS or loopback HTTP")
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "response_format": {"type": "json_object"}}).encode()
    request = urllib.request.Request(endpoint, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        # The endpoint scheme is constrained above.
        with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    return str(body["choices"][0]["message"]["content"])


def _decode_response(response: str) -> tuple[str, str | None]:
    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        return "", f"response is not strict JSON: {exc}"
    if set(data) != {"c_source"} or not isinstance(data["c_source"], str):
        return "", "response must contain only a string c_source field"
    return data["c_source"].strip(), None


def _validate_source(source: str, graph: FlowGraph, tc: Toolchain, round_dir: Path) -> list[str]:
    errors: list[str] = []
    if source.count("transform_candidate") != 1:
        errors.append("proposal must define transform_candidate exactly once")
    if "#include" in source or "```" in source:
        errors.append("proposal contains includes or markdown")
    if FORBIDDEN.search(source):
        errors.append("proposal contains a forbidden operation")
    try:
        proposed = extract_function(source, "transform_candidate")
    except Exception as exc:
        errors.append(f"function extraction failed: {exc}")
        return errors
    calls = [name for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", proposed.body) if name not in {"if", "for", "while", "switch", "sizeof"}]
    if calls:
        errors.append("proposal contains function calls: " + ", ".join(sorted(set(calls))))
    if not re.search(r"void\s+transform_candidate\s*\(\s*float\s*\*\s*dst\s*,\s*const\s+float\s*\*\s*src\s*,\s*size_t\s+n\s*\)", proposed.signature):
        errors.append("function signature differs from the required ABI")
    round_dir.mkdir(parents=True, exist_ok=True)
    c_path = round_dir / "proposal.c"
    c_path.write_text("#include <stddef.h>\n" + source + "\n")
    syntax = run([tc.compiler, "-std=c99", "-O3", "-march=native", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", str(c_path)], timeout=30)
    if syntax.returncode != 0:
        errors.append("Clang rejected proposal: " + (syntax.stdout + syntax.stderr)[-1500:])
    proposed_graph = build_flow_graph(proposed)
    if proposed_graph.canonical != graph.canonical:
        errors.append(f"canonical shape mismatch: expected {graph.canonical}, got {proposed_graph.canonical}")
    errors.extend(_parameter_mismatches(graph, proposed))
    return errors


def _parameter_mismatches(graph: FlowGraph, proposed: Any) -> list[str]:
    expected = graph.source_pattern
    if graph.canonical == "affine":
        actual = detect_affine(proposed)
        if not actual or (actual.mul, actual.add) != (expected.get("mul"), expected.get("add")):
            return ["affine constants or operation order do not match the graph"]
    elif graph.canonical == "saturating_projection":
        actual = detect_clamp(proposed)
        if not actual or (actual.low, actual.high) != (expected.get("low"), expected.get("high")):
            return ["clamp bounds or ordered comparisons do not match the graph"]
    elif graph.canonical == "div_const":
        actual = detect_div_power2(proposed)
        if not actual or actual.divisor != expected.get("divisor"):
            return ["division constant does not match the graph"]
    return []


def _proof_name(canonical: str) -> str:
    if canonical == "affine":
        return "affine_identity"
    if canonical == "saturating_projection":
        return "clamp_branchless"
    if canonical == "div_const":
        return "identity"
    return "identity"
