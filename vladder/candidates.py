from __future__ import annotations

from dataclasses import dataclass, field
import math
import re

from .extractor import ExtractedFunction


@dataclass(frozen=True)
class Candidate:
    name: str
    source: str
    cflags: tuple[str, ...] = ()
    requires_no_alias: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)
    proof: str = "unknown"


@dataclass(frozen=True)
class ClampPattern:
    low: str
    high: str
    index: str
    value: str


@dataclass(frozen=True)
class AffinePattern:
    mul: str
    add: str
    index: str


@dataclass(frozen=True)
class DivPattern:
    divisor: str
    multiplier: str
    index: str


def _float_const(value: str) -> str:
    value = value.strip()
    if value.endswith(("f", "F")):
        return value
    return value + "f"


def detect_clamp(fn: ExtractedFunction) -> ClampPattern | None:
    body = re.sub(r"\s+", " ", fn.body)
    loop = re.search(r"for\s*\([^;]*\b(size_t\s+)?(?P<idx>[A-Za-z_]\w*)\s*=\s*0\s*;[^;]*\b(?P=idx)\s*<\s*n\s*;[^)]*\)", body)
    if not loop:
        return None
    idx = loop.group("idx")
    value_match = re.search(rf"\bfloat\s+(?P<val>[A-Za-z_]\w*)\s*=\s*src\s*\[\s*{idx}\s*\]\s*;", body)
    val = value_match.group("val") if value_match else "x"
    pattern = re.search(
        rf"if\s*\(\s*{val}\s*<\s*(?P<low>[-+]?\d+(?:\.\d+)?f?)\s*\)\s*"
        rf"(?:\{{\s*)?dst\s*\[\s*{idx}\s*\]\s*=\s*(?P=low)\s*;\s*(?:\}}\s*)?"
        rf"else\s+if\s*\(\s*{val}\s*>\s*(?P<high>[-+]?\d+(?:\.\d+)?f?)\s*\)\s*"
        rf"(?:\{{\s*)?dst\s*\[\s*{idx}\s*\]\s*=\s*(?P=high)\s*;\s*(?:\}}\s*)?"
        rf"else\s*(?:\{{\s*)?dst\s*\[\s*{idx}\s*\]\s*=\s*{val}\s*;",
        body,
    )
    if not pattern:
        return None
    return ClampPattern(_float_const(pattern.group("low")), _float_const(pattern.group("high")), idx, val)


def detect_affine(fn: ExtractedFunction) -> AffinePattern | None:
    body = re.sub(r"\s+", " ", fn.body)
    pattern = re.search(
        r"for\s*\([^;]*\b(size_t\s+)?(?P<idx>[A-Za-z_]\w*)\s*=\s*0\s*;[^;]*\b(?P=idx)\s*<\s*n\s*;[^)]*\)"
        r"\s*\{?\s*dst\s*\[\s*(?P=idx)\s*\]\s*=\s*src\s*\[\s*(?P=idx)\s*\]\s*\*\s*(?P<mul>[-+]?\d+(?:\.\d+)?f?)\s*\+\s*(?P<add>[-+]?\d+(?:\.\d+)?f?)\s*;",
        body,
    )
    if pattern:
        return AffinePattern(_float_const(pattern.group("mul")), _float_const(pattern.group("add")), pattern.group("idx"))
    pattern = re.search(
        r"for\s*\([^;]*\b(size_t\s+)?(?P<idx>[A-Za-z_]\w*)\s*=\s*0\s*;[^;]*\b(?P=idx)\s*<\s*n\s*;[^)]*\)"
        r"\s*\{?\s*dst\s*\[\s*(?P=idx)\s*\]\s*=\s*src\s*\[\s*(?P=idx)\s*\]\s*\+\s*(?P<add>[-+]?\d+(?:\.\d+)?f?)\s*;",
        body,
    )
    if pattern:
        return AffinePattern("1.0f", _float_const(pattern.group("add")), pattern.group("idx"))
    return None


def detect_div_power2(fn: ExtractedFunction) -> DivPattern | None:
    body = re.sub(r"\s+", " ", fn.body)
    pattern = re.search(
        r"for\s*\([^;]*\b(size_t\s+)?(?P<idx>[A-Za-z_]\w*)\s*=\s*0\s*;[^;]*\b(?P=idx)\s*<\s*n\s*;[^)]*\)"
        r"\s*\{?\s*dst\s*\[\s*(?P=idx)\s*\]\s*=\s*src\s*\[\s*(?P=idx)\s*\]\s*/\s*(?P<div>[-+]?\d+(?:\.\d+)?f?)\s*;",
        body,
    )
    if not pattern:
        return None
    divisor = float(pattern.group("div").rstrip("fF"))
    if divisor == 0.0:
        return None
    log2 = math.log2(abs(divisor)) if divisor else 0.0
    if abs(log2 - round(log2)) > 1e-12:
        return None
    reciprocal = 1.0 / divisor
    return DivPattern(_float_const(pattern.group("div")), f"{reciprocal:.9g}f", pattern.group("idx"))


def _clamp_scalar(name: str, low: str, high: str, unroll: int = 1) -> str:
    def op(expr: str) -> str:
        return (
            f"float x = src[{expr}];\n"
            f"        dst[{expr}] = x < {low} ? {low} : (x > {high} ? {high} : x);"
        )

    if unroll == 1:
        return f"""
__attribute__((noinline))
void transform_candidate(float *dst, const float *src, size_t n) {{
    for (size_t i = 0; i < n; ++i) {{
        {op("i")}
    }}
}}
"""
    ops = "\n".join(f"        {{\n        {op(f'i + {j}')}\n        }}" for j in range(unroll))
    return f"""
__attribute__((noinline))
void transform_candidate(float *dst, const float *src, size_t n) {{
    size_t i = 0;
    for (; i + {unroll - 1} < n; i += {unroll}) {{
{ops}
    }}
    for (; i < n; ++i) {{
        {op("i")}
    }}
}}
"""


def _clamp_avx2(low: str, high: str) -> str:
    return f"""
__attribute__((noinline))
void transform_candidate(float * __restrict dst, const float * __restrict src, size_t n) {{
    size_t i = 0;
    const __m256 vlo = _mm256_set1_ps({low});
    const __m256 vhi = _mm256_set1_ps({high});
    for (; i + 7 < n; i += 8) {{
        __m256 x = _mm256_loadu_ps(src + i);
        __m256 lt = _mm256_cmp_ps(x, vlo, _CMP_LT_OQ);
        __m256 gt = _mm256_cmp_ps(x, vhi, _CMP_GT_OQ);
        __m256 y = _mm256_blendv_ps(x, vlo, lt);
        y = _mm256_blendv_ps(y, vhi, gt);
        _mm256_storeu_ps(dst + i, y);
    }}
    for (; i < n; ++i) {{
        float x = src[i];
        dst[i] = x < {low} ? {low} : (x > {high} ? {high} : x);
    }}
}}
"""


def _clamp_avx512(low: str, high: str) -> str:
    return f"""
__attribute__((noinline))
void transform_candidate(float * __restrict dst, const float * __restrict src, size_t n) {{
    size_t i = 0;
    const __m512 vlo = _mm512_set1_ps({low});
    const __m512 vhi = _mm512_set1_ps({high});
    for (; i + 15 < n; i += 16) {{
        __m512 x = _mm512_loadu_ps(src + i);
        __mmask16 lt = _mm512_cmp_ps_mask(x, vlo, _CMP_LT_OQ);
        __mmask16 gt = _mm512_cmp_ps_mask(x, vhi, _CMP_GT_OQ);
        __m512 y = _mm512_mask_mov_ps(x, lt, vlo);
        y = _mm512_mask_mov_ps(y, gt, vhi);
        _mm512_storeu_ps(dst + i, y);
    }}
    for (; i < n; ++i) {{
        float x = src[i];
        dst[i] = x < {low} ? {low} : (x > {high} ? {high} : x);
    }}
}}
"""


def _affine_scalar(mul: str, add: str, unroll: int = 1) -> str:
    if unroll == 1:
        return f"""
__attribute__((noinline))
void transform_candidate(float *dst, const float *src, size_t n) {{
    for (size_t i = 0; i < n; ++i) {{
        dst[i] = src[i] * {mul} + {add};
    }}
}}
"""
    ops = "\n".join(f"        dst[i + {j}] = src[i + {j}] * {mul} + {add};" for j in range(unroll))
    return f"""
__attribute__((noinline))
void transform_candidate(float *dst, const float *src, size_t n) {{
    size_t i = 0;
    for (; i + {unroll - 1} < n; i += {unroll}) {{
{ops}
    }}
    for (; i < n; ++i) {{
        dst[i] = src[i] * {mul} + {add};
    }}
}}
"""


def _affine_avx2(mul: str, add: str) -> str:
    return f"""
__attribute__((noinline))
void transform_candidate(float * __restrict dst, const float * __restrict src, size_t n) {{
    size_t i = 0;
    const __m256 vm = _mm256_set1_ps({mul});
    const __m256 va = _mm256_set1_ps({add});
    for (; i + 7 < n; i += 8) {{
        __m256 x = _mm256_loadu_ps(src + i);
        __m256 y = _mm256_add_ps(_mm256_mul_ps(x, vm), va);
        _mm256_storeu_ps(dst + i, y);
    }}
    for (; i < n; ++i) {{
        dst[i] = src[i] * {mul} + {add};
    }}
}}
"""


def _affine_avx512(mul: str, add: str) -> str:
    return f"""
__attribute__((noinline))
void transform_candidate(float * __restrict dst, const float * __restrict src, size_t n) {{
    size_t i = 0;
    const __m512 vm = _mm512_set1_ps({mul});
    const __m512 va = _mm512_set1_ps({add});
    for (; i + 15 < n; i += 16) {{
        __m512 x = _mm512_loadu_ps(src + i);
        __m512 y = _mm512_add_ps(_mm512_mul_ps(x, vm), va);
        _mm512_storeu_ps(dst + i, y);
    }}
    for (; i < n; ++i) {{
        dst[i] = src[i] * {mul} + {add};
    }}
}}
"""


def _div_strength_reduce(multiplier: str, unroll: int = 1) -> str:
    return _affine_scalar(multiplier, "0.0f", unroll).replace(f" + 0.0f", "")


def generate_candidates(fn: ExtractedFunction, cpu_flags: set[str], assume_no_alias: bool) -> list[Candidate]:
    candidates = [
        Candidate(
            "baseline_o3",
            "__attribute__((noinline))\n" + fn.renamed("transform_candidate"),
            tags=("original", "-O3", "-march=native"),
            proof="identity",
        ),
        Candidate(
            "compiler_funroll_loops",
            "__attribute__((noinline))\n" + fn.renamed("transform_candidate"),
            cflags=("-funroll-loops",),
            tags=("original", "compiler-variant", "unroll"),
            proof="identity",
        ),
    ]

    clamp = detect_clamp(fn)
    if clamp:
        candidates.extend(
            [
                Candidate("scalar_branchless", _clamp_scalar("scalar_branchless", clamp.low, clamp.high), tags=("branchless",), proof="clamp_branchless"),
                Candidate("unroll4_branchless", _clamp_scalar("unroll4_branchless", clamp.low, clamp.high, 4), tags=("branchless", "unroll4"), proof="clamp_branchless_unroll"),
                Candidate("unroll8_branchless", _clamp_scalar("unroll8_branchless", clamp.low, clamp.high, 8), tags=("branchless", "unroll8"), proof="clamp_branchless_unroll"),
            ]
        )
        if assume_no_alias and "avx2" in cpu_flags:
            candidates.append(Candidate("avx2_blend", _clamp_avx2(clamp.low, clamp.high), ("-mavx2",), True, ("AVX2", "branchless"), proof="clamp_branchless_vector"))
        if assume_no_alias and "avx512f" in cpu_flags:
            candidates.append(Candidate("avx512_blend", _clamp_avx512(clamp.low, clamp.high), ("-mavx512f",), True, ("AVX512", "branchless"), proof="clamp_branchless_vector"))

    affine = detect_affine(fn)
    if affine:
        candidates.extend(
            [
                Candidate("scalar_affine", _affine_scalar(affine.mul, affine.add), tags=("affine",), proof="affine_identity"),
                Candidate("unroll4_affine", _affine_scalar(affine.mul, affine.add, 4), tags=("affine", "unroll4"), proof="affine_unroll"),
                Candidate("unroll8_affine", _affine_scalar(affine.mul, affine.add, 8), tags=("affine", "unroll8"), proof="affine_unroll"),
            ]
        )
        if assume_no_alias and "avx2" in cpu_flags:
            candidates.append(Candidate("avx2_affine", _affine_avx2(affine.mul, affine.add), ("-mavx2",), True, ("AVX2", "affine"), proof="affine_vector"))
        if assume_no_alias and "avx512f" in cpu_flags:
            candidates.append(Candidate("avx512_affine", _affine_avx512(affine.mul, affine.add), ("-mavx512f",), True, ("AVX512", "affine"), proof="affine_vector"))

    div = detect_div_power2(fn)
    if div:
        candidates.extend(
            [
                Candidate("strength_reduce_mul", _div_strength_reduce(div.multiplier), tags=("strength-reduction",), proof="fp_div_power2_to_mul"),
                Candidate("strength_reduce_unroll4", _div_strength_reduce(div.multiplier, 4), tags=("strength-reduction", "unroll4"), proof="fp_div_power2_to_mul_unroll"),
                Candidate("strength_reduce_unroll8", _div_strength_reduce(div.multiplier, 8), tags=("strength-reduction", "unroll8"), proof="fp_div_power2_to_mul_unroll"),
            ]
        )
        if assume_no_alias and "avx2" in cpu_flags:
            candidates.append(Candidate("avx2_strength_reduce", _affine_avx2(div.multiplier, "0.0f").replace("), va)", "), _mm256_setzero_ps())"), ("-mavx2",), True, ("AVX2", "strength-reduction"), proof="fp_div_power2_to_mul_vector"))
        if assume_no_alias and "avx512f" in cpu_flags:
            candidates.append(Candidate("avx512_strength_reduce", _affine_avx512(div.multiplier, "0.0f").replace("), va)", "), _mm512_setzero_ps())"), ("-mavx512f",), True, ("AVX512", "strength-reduction"), proof="fp_div_power2_to_mul_vector"))

    return candidates
