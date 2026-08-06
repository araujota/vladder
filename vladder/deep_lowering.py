from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from .deep_grammar import DeepDerivation, DeepGrammar, load_deep_grammar
from .deep_ir import DeepKernelContract, build_deep_realization_graph
from .language_adapter import SemanticObligation, obligation


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
    language_obligations: tuple[SemanticObligation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "compiler_flags": list(self.compiler_flags),
            "language_obligations": [asdict(item) for item in self.language_obligations],
        }


def _emitter_obligations(language: str, statements: tuple[tuple[str, str, str], ...]) -> tuple[SemanticObligation, ...]:
    return tuple(
        obligation(
            f"deep.emitter.{language}.{identifier}",
            category,
            statement,
            scope="generated-function",
            proof_method="native-source-binding-and-differential-execution",
            language=language,
            native_construct=identifier,
        )
        for identifier, category, statement in statements
    )


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


def emit_cpp_candidate(contract: DeepKernelContract, realization: str, function: str) -> str:
    """Emit the C physical realization through a C++20, noexcept ABI boundary."""
    source = emit_c_candidate(contract, realization, function)
    exported = re.compile(rf"(?m)^size_t\s+{re.escape(function)}\s*\(")
    source, count = exported.subn(f'extern "C" size_t {function}(', source, count=1)
    if count != 1:
        raise ValueError(f"could not identify exported C++ function {function}")
    signature_end = re.compile(rf'(extern "C" size_t\s+{re.escape(function)}\s*\([^)]*\))\s*\{{')
    source, count = signature_end.subn(r"\1 noexcept {", source, count=1)
    if count != 1:
        raise ValueError(f"could not attach noexcept to exported C++ function {function}")
    return source


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


def _zig_predicate(contract: DeepKernelContract, value: str) -> str:
    if contract.predicate == "equal-u8":
        return f"({value} == needle)"
    return f"(({value} & 0xC0) != 0x80)"


def _zig_scalar(contract: DeepKernelContract, function: str) -> str:
    predicate = _zig_predicate(contract, "data[i]")
    needle_use = "" if contract.predicate == "equal-u8" else "\n    _ = needle;"
    return f"""
export fn {function}(data_ptr: [*]const u8, n: usize, needle: u8) callconv(.c) usize {{
    const data = data_ptr[0..n];{needle_use}
    var count: usize = 0;
    var i: usize = 0;
    while (i < data.len) : (i += 1) {{
        count += @intFromBool({predicate});
    }}
    return count;
}}
""".strip() + "\n"


def _zig_word(contract: DeepKernelContract, function: str) -> str:
    suffix = _safe_identifier(function)
    if contract.predicate == "equal-u8":
        helper = f"""
inline fn vladder_word_equal_{suffix}(lhs: u64, rhs: u64) u64 {{
    const lo: u64 = 0x0101010101010101;
    const hi: u64 = 0x8080808080808080;
    const x = lhs ^ rhs;
    return ~((((x & ~hi) +% ~hi) | x) >> 7) & lo;
}}
"""
        packed = f"vladder_word_equal_{suffix}(word, splat)"
        splat = "const splat: u64 = @as(u64, needle) * 0x0101010101010101;"
    else:
        helper = f"""
inline fn vladder_utf8_leading_{suffix}(values: u64) u64 {{
    return ((~values >> 7) | (values >> 6)) & 0x0101010101010101;
}}
"""
        packed = f"vladder_utf8_leading_{suffix}(word)"
        splat = "_ = needle;"
    tail = _zig_predicate(contract, "data[i]")
    return f"""
{helper.strip()}

export fn {function}(data_ptr: [*]const u8, n: usize, needle: u8) callconv(.c) usize {{
    const data = data_ptr[0..n];
    var count: usize = 0;
    var i: usize = 0;
    {splat}
    while (data.len - i >= 8) : (i += 8) {{
        // vladder_unaligned_load: indexed assembly preserves the admitted byte footprint.
        var word: u64 = 0;
        inline for (0..8) |lane| word |= @as(u64, data[i + lane]) << @intCast(lane * 8);
        count += @popCount({packed});
    }}
    while (i < data.len) : (i += 1) count += @intFromBool({tail});
    return count;
}}
""".strip() + "\n"


def _zig_vector_predicate(contract: DeepKernelContract, values: str, needles: str) -> str:
    if contract.predicate == "equal-u8":
        return f"({values} == {needles})"
    return f"(({values} & @as(@Vector(32, u8), @splat(0xC0))) != @as(@Vector(32, u8), @splat(0x80)))"


def _zig_simd(contract: DeepKernelContract, function: str, *, guarded: bool, byte_accumulate: bool) -> str:
    suffix = _safe_identifier(function)
    helper = f"{suffix}_vector"
    scalar = _zig_scalar(contract, f"{suffix}_scalar") if guarded else ""
    predicate = _zig_vector_predicate(contract, "values", "needles")
    tail = _zig_predicate(contract, "data[i]")
    if byte_accumulate:
        loop = f"""
    // vladder_lane_byte_accumulate
    while (data.len - i >= 32) {{
        var blocks = (data.len - i) / 32;
        if (blocks > 255) blocks = 255;
        var lanes: @Vector(32, u8) = @splat(0);
        var block: usize = 0;
        while (block < blocks) : (block += 1) {{
            const values: @Vector(32, u8) = data[i..][0..32].*;
            const matches = {predicate};
            lanes +%= @select(u8, matches, @as(@Vector(32, u8), @splat(1)), @as(@Vector(32, u8), @splat(0)));
            i += 32;
        }}
        const partial: [32]u8 = lanes;
        inline for (partial) |value| count += value;
    }}
"""
    else:
        loop = f"""
    // vladder_mask_popcount
    while (data.len - i >= 32) : (i += 32) {{
        const values: @Vector(32, u8) = data[i..][0..32].*;
        const matches = {predicate};
        const mask: u32 = @bitCast(matches);
        count += @popCount(mask);
    }}
"""
    needle_setup = (
        "const needles: @Vector(32, u8) = @splat(needle);"
        if contract.predicate == "equal-u8"
        else "_ = needle;"
    )
    helper_source = f"""
inline fn {helper}(data: []const u8, needle: u8) usize {{
    var count: usize = 0;
    var i: usize = 0;
    {needle_setup}
{loop.rstrip()}
    while (i < data.len) : (i += 1) count += @intFromBool({tail});
    return count;
}}
"""
    if guarded:
        wrapper = f"""
export fn {function}(data_ptr: [*]const u8, n: usize, needle: u8) callconv(.c) usize {{
    const vladder_deployment_avx2 = @import("builtin").cpu.arch == .x86_64;
    if (vladder_deployment_avx2) return {helper}(data_ptr[0..n], needle);
    return {suffix}_scalar(data_ptr, n, needle);
}}
"""
    else:
        wrapper = f"""
export fn {function}(data_ptr: [*]const u8, n: usize, needle: u8) callconv(.c) usize {{
    return {helper}(data_ptr[0..n], needle);
}}
"""
    return f"{scalar.strip()}\n\n{helper_source.strip()}\n\n{wrapper.strip()}\n".lstrip()


def emit_zig_candidate(contract: DeepKernelContract, realization: str, function: str) -> str:
    if realization == "scalar":
        return _zig_scalar(contract, function)
    if realization == "word-swar":
        return _zig_word(contract, function)
    if realization == "simd-mask-popcount":
        return _zig_simd(contract, function, guarded=False, byte_accumulate=False)
    if realization == "simd-byte-accumulate-final":
        return _zig_simd(contract, function, guarded=False, byte_accumulate=True)
    if realization == "guarded-avx2":
        return _zig_simd(contract, function, guarded=True, byte_accumulate=False)
    if realization == "guarded-avx2-byte":
        return _zig_simd(contract, function, guarded=True, byte_accumulate=True)
    raise ValueError(f"no Zig emitter for realization: {realization}")


def _julia_predicate(contract: DeepKernelContract, value: str) -> str:
    if contract.predicate == "equal-u8":
        return f"({value} == needle)"
    return f"(({value} & 0xc0) != 0x80)"


def _julia_scalar(contract: DeepKernelContract, function: str) -> str:
    predicate = _julia_predicate(contract, "data[i]")
    return f"""
Base.@noinline function {function}(data::Vector{{UInt8}}, needle::UInt8)::Int
    count = 0
    @inbounds for i in eachindex(data)
        count += {predicate}
    end
    return count
end
""".strip() + "\n"


def _julia_word(contract: DeepKernelContract, function: str) -> str:
    suffix = _safe_identifier(function)
    if contract.predicate == "equal-u8":
        helper = f"""
@inline function vladder_word_equal_{suffix}(lhs::UInt64, rhs::UInt64)::UInt64
    lo = UInt64(0x0101010101010101)
    hi = UInt64(0x8080808080808080)
    x = xor(lhs, rhs)
    return ~((((x & ~hi) + ~hi) | x) >> 7) & lo
end
"""
        packed = f"vladder_word_equal_{suffix}(word, splat)"
        splat = "splat = UInt64(needle) * UInt64(0x0101010101010101)"
    else:
        helper = f"""
@inline function vladder_utf8_leading_{suffix}(values::UInt64)::UInt64
    return ((~values >> 7) | (values >> 6)) & UInt64(0x0101010101010101)
end
"""
        packed = f"vladder_utf8_leading_{suffix}(word)"
        splat = "nothing"
    tail = _julia_predicate(contract, "data[i]")
    lane_lines = "\n".join(f"        word |= UInt64(data[i + {lane}]) << {lane * 8}" for lane in range(8))
    return f"""
{helper.strip()}

Base.@noinline function {function}(data::Vector{{UInt8}}, needle::UInt8)::Int
    count = 0
    i = 1
    {splat}
    while length(data) - i + 1 >= 8
        # vladder_unaligned_load
        word = UInt64(0)
{lane_lines}
        count += count_ones({packed})
        i += 8
    end
    @inbounds while i <= length(data)
        count += {tail}
        i += 1
    end
    return count
end
""".strip() + "\n"


def _julia_simd(contract: DeepKernelContract, function: str, *, guarded: bool, byte_accumulate: bool) -> str:
    suffix = _safe_identifier(function)
    helper = f"{suffix}_vector"
    scalar = _julia_scalar(contract, f"{suffix}_scalar") if guarded else ""
    lane_predicates = [_julia_predicate(contract, f"data[i + {lane}]") for lane in range(32)]
    if byte_accumulate:
        declarations = "\n".join(f"        lane_{lane} = UInt8(0)" for lane in range(32))
        updates = "\n".join(f"            lane_{lane} += UInt8({predicate})" for lane, predicate in enumerate(lane_predicates))
        reductions = " + ".join(f"Int(lane_{lane})" for lane in range(32))
        loop = f"""
    # vladder_lane_byte_accumulate
    while length(data) - i + 1 >= 32
        blocks = min(div(length(data) - i + 1, 32), 255)
{declarations}
        for _ in 1:blocks
            @inbounds begin
{updates}
            end
            i += 32
        end
        count += {reductions}
    end
"""
    else:
        mask_lines = "\n".join(f"            mask |= UInt32({predicate}) << {lane}" for lane, predicate in enumerate(lane_predicates))
        loop = f"""
    # vladder_mask_popcount
    while length(data) - i + 1 >= 32
        mask = UInt32(0)
        @inbounds begin
{mask_lines}
        end
        count += count_ones(mask)
        i += 32
    end
"""
    helper_source = f"""
@inline function {helper}(data::Vector{{UInt8}}, needle::UInt8)::Int
    count = 0
    i = 1
{loop.rstrip()}
    @inbounds while i <= length(data)
        count += {_julia_predicate(contract, "data[i]")}
        i += 1
    end
    return count
end
"""
    if guarded:
        wrapper = f"""
Base.@noinline function {function}(data::Vector{{UInt8}}, needle::UInt8)::Int
    vladder_deployment_avx2 = Sys.ARCH === :x86_64
    return vladder_deployment_avx2 ? {helper}(data, needle) : {suffix}_scalar(data, needle)
end
"""
    else:
        wrapper = f"""
Base.@noinline function {function}(data::Vector{{UInt8}}, needle::UInt8)::Int
    return {helper}(data, needle)
end
"""
    return f"{scalar.strip()}\n\n{helper_source.strip()}\n\n{wrapper.strip()}\n".lstrip()


def emit_julia_candidate(contract: DeepKernelContract, realization: str, function: str) -> str:
    if realization == "scalar":
        return _julia_scalar(contract, function)
    if realization == "word-swar":
        return _julia_word(contract, function)
    if realization == "simd-mask-popcount":
        return _julia_simd(contract, function, guarded=False, byte_accumulate=False)
    if realization == "simd-byte-accumulate-final":
        return _julia_simd(contract, function, guarded=False, byte_accumulate=True)
    if realization == "guarded-avx2":
        return _julia_simd(contract, function, guarded=True, byte_accumulate=False)
    if realization == "guarded-avx2-byte":
        return _julia_simd(contract, function, guarded=True, byte_accumulate=True)
    raise ValueError(f"no Julia emitter for realization: {realization}")


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
    if normalized_language not in terminal["languages"]:
        raise ValueError(f"{derivation.target} has no {language} emitter")
    if normalized_language == "c":
        source = emit_c_candidate(contract, derivation.target, function)
        obligations = _emitter_obligations("c", (
            ("object-bounds", "bounds", "the pointer extent contains every scalar and wide load"),
            ("unaligned-load", "memory", "wide loads use memcpy or an ISA-defined unaligned intrinsic"),
            ("target-feature", "target", "the AVX2 guard or deployment target dominates vector execution"),
        ))
        flags = ("-std=c17", "-O3", "-march=native")
    elif normalized_language == "cpp":
        source = emit_cpp_candidate(contract, derivation.target, function)
        obligations = _emitter_obligations("cpp", (
            ("borrowed-pointer", "ownership", "the borrowed pointer extent remains valid for the call"),
            ("noexcept-boundary", "exception", "the generated function does not throw across its noexcept boundary"),
            ("unaligned-load", "memory", "wide loads use memcpy or an ISA-defined unaligned intrinsic"),
            ("target-feature", "target", "the AVX2 guard or deployment target dominates vector execution"),
        ))
        flags = ("-std=c++20", "-O3", "-march=native")
    elif normalized_language == "rust":
        source = emit_rust_candidate(contract, derivation.target, function)
        obligations = _emitter_obligations("rust", (
            ("borrowed-slice", "ownership", "the borrowed slice remains live for the function call"),
            ("wide-load-guard", "bounds", "the slice length guard dominates every wide load"),
            ("unsafe-scope", "safety", "unsafe operations are confined to the target-feature helper"),
            ("panic-free", "exception", "the admitted execution path is panic-free"),
        ))
        flags = ("-C", "opt-level=3", "-C", "target-cpu=native")
    elif normalized_language == "zig":
        source = emit_zig_candidate(contract, derivation.target, function)
        obligations = _emitter_obligations("zig", (
            ("borrowed-many-pointer", "ownership", "the many-pointer extent remains valid for the function call"),
            ("wide-load-guard", "bounds", "the slice length guard dominates every indexed wide load"),
            ("deployment-cpu", "target", "the deployment CPU matches the compiled vector realization"),
            ("total-function", "exception", "the generated kernel allocates nothing and has no error-union exit"),
        ))
        flags = ("-O", "ReleaseFast", "-mcpu", "native")
    elif normalized_language == "julia":
        source = emit_julia_candidate(contract, derivation.target, function)
        obligations = _emitter_obligations("julia", (
            ("rooted-vector", "lifetime", "the Vector{UInt8} remains rooted during generated execution"),
            ("inbounds-guard", "bounds", "each @inbounds access is dominated by its scalar or width guard"),
            ("fixed-uint", "numeric", "UInt8, UInt32, and UInt64 operations retain fixed-width modular semantics"),
            ("deployment-cpu", "target", "the Julia CPU specialization and deployment architecture are recorded"),
        ))
        flags = ("--startup-file=no", "-O3", "--check-bounds=no")
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
