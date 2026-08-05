from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from .deep_grammar import DeepDerivation, DeepGrammar, load_deep_grammar
from .deep_ir import DeepKernelContract, build_deep_realization_graph


@dataclass(frozen=True)
class DeepCandidate:
    id: str
    language: str
    function: str
    realization: str
    source: str
    source_sha256: str
    derivation_hash: str
    graph_hash: str
    compiler_flags: tuple[str, ...]
    language_obligations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "compiler_flags": list(self.compiler_flags), "language_obligations": list(self.language_obligations)}


def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"\W+", "_", value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "vladder_" + cleaned
    return cleaned


def _c_predicate(contract: DeepKernelContract, value: str) -> str:
    if contract.predicate == "equal-u8":
        return f"({value} == needle)"
    return f"(({value} & UINT8_C(0xC0)) != UINT8_C(0x80))"


def _rust_predicate(contract: DeepKernelContract, value: str) -> str:
    if contract.predicate == "equal-u8":
        return f"({value} == needle)"
    return f"(({value} & 0xC0u8) != 0x80u8)"


def _c_scalar(contract: DeepKernelContract, function: str) -> str:
    predicate = _c_predicate(contract, "data[i]")
    return f"""
__attribute__((noinline))
size_t {function}(const uint8_t *data, size_t n, uint8_t needle) {{
    size_t count = 0;
    for (size_t i = 0; i < n; ++i) {{
        count += (size_t){predicate};
    }}
    return count;
}}
""".strip() + "\n"


def _c_word(contract: DeepKernelContract, function: str) -> str:
    suffix = _safe_identifier(function)
    if contract.predicate == "equal-u8":
        packed_expression = f"vladder_word_equal_{suffix}(word, splat)"
        predicate_helper = f"""
static inline uint64_t vladder_word_equal_{suffix}(uint64_t lhs, uint64_t rhs) {{
    const uint64_t lo = UINT64_C(0x0101010101010101);
    const uint64_t hi = UINT64_C(0x8080808080808080);
    const uint64_t x = lhs ^ rhs;
    return ~((((x & ~hi) + ~hi) | x) >> 7) & lo;
}}
"""
    else:
        packed_expression = f"vladder_utf8_leading_{suffix}(word)"
        predicate_helper = f"""
static inline uint64_t vladder_utf8_leading_{suffix}(uint64_t values) {{
    return ((~values >> 7) | (values >> 6)) & UINT64_C(0x0101010101010101);
}}
"""
    scalar_tail = _c_predicate(contract, "data[i]")
    return f"""
{predicate_helper.strip()}

__attribute__((noinline))
size_t {function}(const uint8_t *data, size_t n, uint8_t needle) {{
    size_t count = 0;
    size_t i = 0;
    const uint64_t splat = UINT64_C(0x0101010101010101) * (uint64_t)needle;
    for (; n - i >= 8; i += 8) {{
        uint64_t word;
        memcpy(&word, data + i, sizeof(word));
        const uint64_t lane_bits = {packed_expression};
        count += (size_t)__builtin_popcountll(lane_bits);
    }}
    for (; i < n; ++i) {{
        count += (size_t){scalar_tail};
    }}
    return count;
}}
""".strip() + "\n"


def _c_vector_predicate(contract: DeepKernelContract, vector: str, needle_vector: str) -> str:
    if contract.predicate == "equal-u8":
        return f"_mm256_cmpeq_epi8({vector}, {needle_vector})"
    return f"_mm256_xor_si256(_mm256_cmpeq_epi8(_mm256_and_si256({vector}, _mm256_set1_epi8((char)0xC0)), _mm256_set1_epi8((char)0x80)), _mm256_set1_epi8((char)-1))"


def _c_simd_mask(contract: DeepKernelContract, function: str, *, guarded: bool) -> str:
    helper = f"{_safe_identifier(function)}_avx2"
    predicate = _c_vector_predicate(contract, "values", "needles")
    tail = _c_predicate(contract, "data[i]")
    scalar = _c_scalar(contract, f"{_safe_identifier(function)}_scalar") if guarded else ""
    wrapper = f"""
__attribute__((noinline))
size_t {function}(const uint8_t *data, size_t n, uint8_t needle) {{
    if (__builtin_cpu_supports("avx2")) {{
        return {helper}(data, n, needle);
    }}
    return {_safe_identifier(function)}_scalar(data, n, needle);
}}
""" if guarded else f"""
__attribute__((noinline))
size_t {function}(const uint8_t *data, size_t n, uint8_t needle) {{
    return {helper}(data, n, needle);
}}
"""
    return f"""
{scalar.strip()}

__attribute__((target("avx2"), noinline))
static size_t {helper}(const uint8_t *data, size_t n, uint8_t needle) {{
    size_t count = 0;
    size_t i = 0;
    const __m256i needles = _mm256_set1_epi8((char)needle);
    for (; n - i >= 32; i += 32) {{
        const __m256i values = _mm256_loadu_si256((const __m256i *)(const void *)(data + i));
        const __m256i matches = {predicate};
        const uint32_t mask = (uint32_t)_mm256_movemask_epi8(matches);
        count += (size_t)__builtin_popcount(mask);
    }}
    for (; i < n; ++i) {{
        count += (size_t){tail};
    }}
    return count;
}}

{wrapper.strip()}
""".strip() + "\n"


def _c_simd_byte(contract: DeepKernelContract, function: str, *, guarded: bool) -> str:
    helper = f"{_safe_identifier(function)}_avx2"
    predicate = _c_vector_predicate(contract, "values", "needles")
    tail = _c_predicate(contract, "data[i]")
    scalar = _c_scalar(contract, f"{_safe_identifier(function)}_scalar") if guarded else ""
    wrapper = f"""
__attribute__((noinline))
size_t {function}(const uint8_t *data, size_t n, uint8_t needle) {{
    if (__builtin_cpu_supports("avx2")) return {helper}(data, n, needle);
    return {_safe_identifier(function)}_scalar(data, n, needle);
}}
""" if guarded else f"__attribute__((noinline))\nsize_t {function}(const uint8_t *data, size_t n, uint8_t needle) {{ return {helper}(data, n, needle); }}"
    return f"""
{scalar.strip()}

__attribute__((target("avx2"), noinline))
static size_t {helper}(const uint8_t *data, size_t n, uint8_t needle) {{
    size_t count = 0;
    size_t i = 0;
    const __m256i needles = _mm256_set1_epi8((char)needle);
    const __m256i zero = _mm256_setzero_si256();
    while (n - i >= 32) {{
        size_t blocks = (n - i) / 32;
        if (blocks > 255) blocks = 255;
        __m256i lanes = zero;
        for (size_t block = 0; block < blocks; ++block) {{
            const __m256i values = _mm256_loadu_si256((const __m256i *)(const void *)(data + i));
            const __m256i matches = {predicate};
            lanes = _mm256_sub_epi8(lanes, matches);
            i += 32;
        }}
        const __m256i sums = _mm256_sad_epu8(lanes, zero);
        uint64_t partial[4];
        _mm256_storeu_si256((__m256i *)(void *)partial, sums);
        count += (size_t)(partial[0] + partial[1] + partial[2] + partial[3]);
    }}
    for (; i < n; ++i) count += (size_t){tail};
    return count;
}}

{wrapper.strip()}
""".strip() + "\n"


def emit_c_candidate(contract: DeepKernelContract, realization: str, function: str) -> str:
    if realization == "scalar":
        return _c_scalar(contract, function)
    if realization == "word-swar":
        return _c_word(contract, function)
    if realization == "simd-mask-popcount":
        return _c_simd_mask(contract, function, guarded=False)
    if realization == "simd-byte-accumulate-final":
        return _c_simd_byte(contract, function, guarded=False)
    if realization == "guarded-avx2":
        return _c_simd_mask(contract, function, guarded=True)
    if realization == "guarded-avx2-byte":
        return _c_simd_byte(contract, function, guarded=True)
    raise ValueError(f"no C emitter for realization: {realization}")


def _rust_scalar(contract: DeepKernelContract, function: str) -> str:
    predicate = _rust_predicate(contract, "value")
    needle_use = "" if contract.predicate == "equal-u8" else "\n    let _ = needle;"
    return f"""
#[no_mangle]
#[inline(never)]
pub fn {function}(data: &[u8], needle: u8) -> usize {{{needle_use}
    let mut count = 0usize;
    for &value in data {{
        count += {predicate} as usize;
    }}
    count
}}
""".strip() + "\n"


def _rust_word(contract: DeepKernelContract, function: str) -> str:
    suffix = _safe_identifier(function)
    if contract.predicate == "equal-u8":
        helper = f"""
#[inline(always)]
fn vladder_word_equal_{suffix}(lhs: u64, rhs: u64) -> u64 {{
    let lo = 0x0101_0101_0101_0101u64;
    let hi = 0x8080_8080_8080_8080u64;
    let x = lhs ^ rhs;
    !((((x & !hi).wrapping_add(!hi)) | x) >> 7) & lo
}}
"""
        packed = f"vladder_word_equal_{suffix}(word, splat)"
    else:
        helper = f"""
#[inline(always)]
fn vladder_utf8_leading_{suffix}(values: u64) -> u64 {{
    ((!values >> 7) | (values >> 6)) & 0x0101_0101_0101_0101u64
}}
"""
        packed = f"vladder_utf8_leading_{suffix}(word)"
    tail = _rust_predicate(contract, "data[i]")
    splat_declaration = "let splat = 0x0101_0101_0101_0101u64.wrapping_mul(needle as u64);" if contract.predicate == "equal-u8" else "let _ = needle;"
    return f"""
{helper.strip()}

#[no_mangle]
#[inline(never)]
pub fn {function}(data: &[u8], needle: u8) -> usize {{
    let mut count = 0usize;
    let mut i = 0usize;
    {splat_declaration}
    while data.len() - i >= 8 {{
        let word = u64::from_ne_bytes(data[i..i + 8].try_into().unwrap());
        count += ({packed}).count_ones() as usize;
        i += 8;
    }}
    while i < data.len() {{
        count += {tail} as usize;
        i += 1;
    }}
    count
}}
""".strip() + "\n"


def _rust_vector_predicate(contract: DeepKernelContract, vector: str, needles: str) -> str:
    if contract.predicate == "equal-u8":
        return f"_mm256_cmpeq_epi8({vector}, {needles})"
    return f"_mm256_xor_si256(_mm256_cmpeq_epi8(_mm256_and_si256({vector}, _mm256_set1_epi8(0xC0u8 as i8)), _mm256_set1_epi8(0x80u8 as i8)), _mm256_set1_epi8(-1))"


def _rust_simd(contract: DeepKernelContract, function: str, *, guarded: bool, byte_accumulate: bool) -> str:
    helper = f"{_safe_identifier(function)}_avx2"
    scalar_name = f"{_safe_identifier(function)}_scalar"
    predicate = _rust_vector_predicate(contract, "values", "needles")
    tail = _rust_predicate(contract, "data[i]")
    scalar = _rust_scalar(contract, scalar_name) if guarded else ""
    if byte_accumulate:
        body = f"""
    let zero = _mm256_setzero_si256();
    while data.len() - i >= 32 {{
        let mut blocks = (data.len() - i) / 32;
        if blocks > 255 {{ blocks = 255; }}
        let mut lanes = zero;
        for _ in 0..blocks {{
            let values = _mm256_loadu_si256(data.as_ptr().add(i) as *const __m256i);
            let matches = {predicate};
            lanes = _mm256_sub_epi8(lanes, matches);
            i += 32;
        }}
        let sums = _mm256_sad_epu8(lanes, zero);
        let mut partial = [0u64; 4];
        _mm256_storeu_si256(partial.as_mut_ptr() as *mut __m256i, sums);
        count += partial.iter().copied().sum::<u64>() as usize;
    }}
"""
        imports = "__m256i, _mm256_cmpeq_epi8, _mm256_loadu_si256, _mm256_sad_epu8, _mm256_set1_epi8, _mm256_setzero_si256, _mm256_storeu_si256, _mm256_sub_epi8"
    else:
        body = f"""
    while data.len() - i >= 32 {{
        let values = _mm256_loadu_si256(data.as_ptr().add(i) as *const __m256i);
        let matches = {predicate};
        let mask = _mm256_movemask_epi8(matches) as u32;
        count += mask.count_ones() as usize;
        i += 32;
    }}
"""
        imports = "__m256i, _mm256_cmpeq_epi8, _mm256_loadu_si256, _mm256_movemask_epi8, _mm256_set1_epi8"
    if contract.predicate == "utf8-leading-byte":
        imports += ", _mm256_and_si256, _mm256_xor_si256"
    wrapper = f"""
#[no_mangle]
#[inline(never)]
pub fn {function}(data: &[u8], needle: u8) -> usize {{
    if std::is_x86_feature_detected!("avx2") {{
        unsafe {{ return {helper}(data, needle); }}
    }}
    {scalar_name}(data, needle)
}}
""" if guarded else f"""
#[no_mangle]
#[inline(never)]
pub fn {function}(data: &[u8], needle: u8) -> usize {{
    unsafe {{ {helper}(data, needle) }}
}}
"""
    return f"""
use std::arch::x86_64::{{{imports}}};

{scalar.strip()}

#[no_mangle]
#[target_feature(enable = "avx2")]
unsafe fn {helper}(data: &[u8], needle: u8) -> usize {{
    let mut count = 0usize;
    let mut i = 0usize;
    let needles = _mm256_set1_epi8(needle as i8);
{body.rstrip()}
    while i < data.len() {{
        count += {tail} as usize;
        i += 1;
    }}
    count
}}

{wrapper.strip()}
""".strip() + "\n"


def emit_rust_candidate(contract: DeepKernelContract, realization: str, function: str) -> str:
    if realization == "scalar":
        return _rust_scalar(contract, function)
    if realization == "word-swar":
        return _rust_word(contract, function)
    if realization == "simd-mask-popcount":
        return _rust_simd(contract, function, guarded=False, byte_accumulate=False)
    if realization == "simd-byte-accumulate-final":
        return _rust_simd(contract, function, guarded=False, byte_accumulate=True)
    if realization == "guarded-avx2":
        return _rust_simd(contract, function, guarded=True, byte_accumulate=False)
    if realization == "guarded-avx2-byte":
        return _rust_simd(contract, function, guarded=True, byte_accumulate=True)
    raise ValueError(f"no Rust emitter for realization: {realization}")


def emit_deep_candidate(
    contract: DeepKernelContract,
    derivation: DeepDerivation,
    language: str,
    function: str,
    grammar: DeepGrammar | None = None,
) -> DeepCandidate:
    grammar = grammar or load_deep_grammar()
    terminal = grammar.terminal(derivation.target)
    normalized_language = "cpp" if language == "c++" else language
    if normalized_language not in terminal["languages"] and not (normalized_language == "cpp" and "c" in terminal["languages"]):
        raise ValueError(f"{derivation.target} has no {language} emitter")
    if normalized_language in {"c", "cpp"}:
        source = emit_c_candidate(contract, derivation.target, function)
        obligations = ("object bounds", "unaligned access through memcpy or intrinsic", "target-feature guard or deployment ISA")
        flags = ("-std=c17", "-O3", "-march=native")
    elif normalized_language == "rust":
        source = emit_rust_candidate(contract, derivation.target, function)
        obligations = ("borrowed slice remains live", "bounds guard dominates wide load", "unsafe block limited to target-feature helper", "panic-free admitted path")
        flags = ("-C", "opt-level=3", "-C", "target-cpu=native")
    else:
        raise ValueError(f"unsupported native emitter language: {language}")
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    graph = build_deep_realization_graph(contract, derivation.target, source_language=normalized_language, function_identity=function)
    candidate_id = hashlib.sha256(f"{derivation.derivation_hash}:{normalized_language}:{source_hash}".encode()).hexdigest()[:20]
    return DeepCandidate(
        candidate_id,
        normalized_language,
        function,
        derivation.target,
        source,
        source_hash,
        derivation.derivation_hash,
        graph.graph_hash,
        flags,
        obligations,
    )
