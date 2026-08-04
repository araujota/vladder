from __future__ import annotations

from .candidates import Candidate, _affine_avx2, _affine_avx512, _affine_scalar, _clamp_avx2, _clamp_avx512, _clamp_scalar, _div_strength_reduce
from .extractor import ExtractedFunction
from .flow import FlowGraph


def _original(fn: ExtractedFunction) -> str:
    return "__attribute__((noinline))\n" + fn.renamed("transform_candidate")


def graph_candidates(fn: ExtractedFunction, graph: FlowGraph, cpu_flags: set[str], assume_no_alias: bool) -> list[Candidate]:
    candidates = [
        Candidate("baseline_o3", _original(fn), tags=("original", "-O3", "-march=native", "graph"), proof="identity"),
        Candidate("compiler_funroll_loops", _original(fn), cflags=("-funroll-loops",), tags=("compiler-variant", "graph"), proof="identity"),
        Candidate("compiler_no_vectorize", _original(fn), cflags=("-fno-vectorize", "-fno-slp-vectorize"), tags=("compiler-variant", "graph", "no-vectorize"), proof="identity"),
    ]
    p = graph.source_pattern
    if graph.canonical == "saturating_projection":
        low = p["low"]
        high = p["high"]
        candidates.append(Candidate("graph_select_clamp", _clamp_scalar("graph_select_clamp", low, high), tags=("graph", "select", "clamp"), proof="clamp_branchless"))
        if assume_no_alias and "avx2" in cpu_flags:
            candidates.append(Candidate("graph_avx2_clamp", _clamp_avx2(low, high), ("-mavx2",), True, ("graph", "AVX2", "clamp"), proof="clamp_branchless_vector"))
        if assume_no_alias and "avx512f" in cpu_flags:
            candidates.append(Candidate("graph_avx512_clamp", _clamp_avx512(low, high), ("-mavx512f",), True, ("graph", "AVX512", "clamp"), proof="clamp_branchless_vector"))
    elif graph.canonical == "affine" and {"mul", "add"} <= p.keys():
        mul = p["mul"]
        add = p["add"]
        candidates.append(Candidate("graph_affine_scalar", _affine_scalar(mul, add), tags=("graph", "affine"), proof="affine_identity"))
        if assume_no_alias and "avx2" in cpu_flags:
            candidates.append(Candidate("graph_avx2_affine", _affine_avx2(mul, add), ("-mavx2",), True, ("graph", "AVX2", "affine"), proof="affine_vector"))
        if assume_no_alias and "avx512f" in cpu_flags:
            candidates.append(Candidate("graph_avx512_affine", _affine_avx512(mul, add), ("-mavx512f",), True, ("graph", "AVX512", "affine"), proof="affine_vector"))
    elif graph.canonical == "div_const" and p.get("exact_power2"):
        div = float(str(p["divisor"]).rstrip("fF"))
        mul = f"{1.0 / div:.9g}f"
        candidates.append(Candidate("graph_strength_reduce_mul", _div_strength_reduce(mul), tags=("graph", "strength-reduction"), proof="fp_div_power2_to_mul"))
        if assume_no_alias and "avx2" in cpu_flags:
            candidates.append(Candidate("graph_avx2_strength_reduce", _affine_avx2(mul, "0.0f").replace("), va)", "), _mm256_setzero_ps())"), ("-mavx2",), True, ("graph", "AVX2", "strength-reduction"), proof="fp_div_power2_to_mul_vector"))
        if assume_no_alias and "avx512f" in cpu_flags:
            candidates.append(Candidate("graph_avx512_strength_reduce", _affine_avx512(mul, "0.0f").replace("), va)", "), _mm512_setzero_ps())"), ("-mavx512f",), True, ("graph", "AVX512", "strength-reduction"), proof="fp_div_power2_to_mul_vector"))
    return candidates
