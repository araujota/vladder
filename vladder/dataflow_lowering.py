from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .dataflow_grammar import BoundedDataflowGrammar, DataflowDerivation, load_bounded_dataflow_grammar
from .dataflow_ir import BoundedDataflowContract, build_bounded_dataflow_graph
from .language_adapter import SemanticObligation, obligation


@dataclass(frozen=True)
class DataflowCandidate:
    id: str
    language: str
    function: str
    family: str
    realization: str
    source: str
    source_sha256: str
    derivation_hash: str
    graph_hash: str
    compiler_flags: tuple[str, ...]
    obligations: tuple[SemanticObligation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "compiler_flags": list(self.compiler_flags),
            "obligations": [asdict(item) for item in self.obligations],
        }


def _preamble() -> str:
    return """#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <immintrin.h>
#include <limits>
"""


def _write_lines(contract: BoundedDataflowContract, index: str, value: str, output: str) -> str:
    lines = []
    if contract.output_mode in {"index-only", "index-value"}:
        lines.append(f"if (out_indices != nullptr) out_indices[{output}] = static_cast<std::uint32_t>({index});")
    if contract.output_mode in {"value-only", "index-value"}:
        lines.append(f"if (out_values != nullptr) out_values[{output}] = {value};")
    return "\n        ".join(lines)


def _capacity_limit(contract: BoundedDataflowContract) -> str:
    if contract.capacity_policy == "fail-unchanged":
        return "if (selected > capacity) return std::numeric_limits<std::size_t>::max();\n    const std::size_t limit = selected;"
    return "const std::size_t limit = std::min(selected, capacity);"


def _compaction_scalar(contract: BoundedDataflowContract, function: str, *, static_name: str | None = None) -> str:
    name = static_name or function
    linkage = "static" if static_name else 'extern "C"'
    write = _write_lines(contract, "i", "current[i]", "output")
    return f"""
{linkage} std::size_t {name}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    std::size_t selected = 0;
    for (std::size_t i = 0; i < n; ++i) selected += current[i] != baseline[i];
    {_capacity_limit(contract)}
    std::size_t output = 0;
    for (std::size_t i = 0; i < n && output < limit; ++i) {{
        if (current[i] == baseline[i]) continue;
        {write}
        ++output;
    }}
    return output;
}}
"""


def _compaction_mask(contract: BoundedDataflowContract, function: str) -> str:
    write = _write_lines(contract, "i", "current[i]", "output")
    return f"""
extern "C" std::size_t {function}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    std::size_t selected = 0;
    for (std::size_t base = 0; base < n; base += 64) {{
        std::uint64_t mask = 0;
        const std::size_t lanes = std::min<std::size_t>(64, n - base);
        for (std::size_t lane = 0; lane < lanes; ++lane)
            mask |= static_cast<std::uint64_t>(current[base + lane] != baseline[base + lane]) << lane;
        selected += static_cast<std::size_t>(std::popcount(mask));
    }}
    {_capacity_limit(contract)}
    std::size_t output = 0;
    for (std::size_t base = 0; base < n && output < limit; base += 64) {{
        std::uint64_t mask = 0;
        const std::size_t lanes = std::min<std::size_t>(64, n - base);
        for (std::size_t lane = 0; lane < lanes; ++lane)
            mask |= static_cast<std::uint64_t>(current[base + lane] != baseline[base + lane]) << lane;
        while (mask != 0 && output < limit) {{
            const std::size_t lane = static_cast<std::size_t>(std::countr_zero(mask));
            const std::size_t i = base + lane;
            {write}
            ++output;
            mask &= mask - 1;
        }}
    }}
    return output;
}}
"""


def _compaction_fused(contract: BoundedDataflowContract, function: str) -> str:
    scalar = f"{function}_two_pass"
    write = _write_lines(contract, "i", "current[i]", "output")
    if contract.capacity_policy == "fail-unchanged":
        fallback = f"""
    if (capacity < n)
        return {scalar}(out_indices, out_values, capacity, current, baseline, n);
"""
    else:
        fallback = ""
    return _compaction_scalar(contract, function, static_name=scalar) + f"""
extern "C" std::size_t {function}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    {fallback}
    std::size_t output = 0;
    for (std::size_t i = 0; i < n && output < capacity; ++i) {{
        if (current[i] == baseline[i]) continue;
        {write}
        ++output;
    }}
    return output;
}}
"""


def _compaction_avx2(contract: BoundedDataflowContract, function: str) -> str:
    scalar = f"{function}_scalar"
    vector = f"{function}_avx2"
    write = _write_lines(contract, "logical", "current[logical]", "output")
    tail_write = _write_lines(contract, "i", "current[i]", "output")
    return _compaction_scalar(contract, function, static_name=scalar) + f"""
__attribute__((target("avx2")))
static std::size_t {vector}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    std::size_t selected = 0;
    std::size_t i = 0;
    for (; n - i >= 4; i += 4) {{
        const __m256i lhs = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(current + i));
        const __m256i rhs = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(baseline + i));
        const unsigned equal = static_cast<unsigned>(_mm256_movemask_pd(_mm256_castsi256_pd(_mm256_cmpeq_epi64(lhs, rhs))));
        selected += static_cast<std::size_t>(std::popcount((~equal) & 0xFU));
    }}
    for (; i < n; ++i) selected += current[i] != baseline[i];
    {_capacity_limit(contract)}
    std::size_t output = 0;
    i = 0;
    for (; n - i >= 4 && output < limit; i += 4) {{
        const __m256i lhs = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(current + i));
        const __m256i rhs = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(baseline + i));
        const unsigned equal = static_cast<unsigned>(_mm256_movemask_pd(_mm256_castsi256_pd(_mm256_cmpeq_epi64(lhs, rhs))));
        unsigned mask = (~equal) & 0xFU;
        while (mask != 0 && output < limit) {{
            const std::size_t lane = static_cast<std::size_t>(std::countr_zero(mask));
            const std::size_t logical = i + lane;
            {write}
            ++output;
            mask &= mask - 1;
        }}
    }}
    for (; i < n && output < limit; ++i) {{
        if (current[i] == baseline[i]) continue;
        {tail_write}
        ++output;
    }}
    return output;
}}

extern "C" std::size_t {function}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    if (__builtin_cpu_supports("avx2"))
        return {vector}(out_indices, out_values, capacity, current, baseline, n);
    return {scalar}(out_indices, out_values, capacity, current, baseline, n);
}}
"""


def _compaction_avx512(contract: BoundedDataflowContract, function: str) -> str:
    scalar = f"{function}_scalar"
    vector = f"{function}_avx512"
    write_index = "" if contract.output_mode == "value-only" else "if (out_indices != nullptr) out_indices[output] = static_cast<std::uint32_t>(i + lane);"
    store_values = "" if contract.output_mode == "index-only" else "if (out_values != nullptr) _mm512_mask_compressstoreu_epi64(out_values + output, store_mask, lhs);"
    tail_write = _write_lines(contract, "i", "current[i]", "output")
    return _compaction_scalar(contract, function, static_name=scalar) + f"""
__attribute__((target("avx512f")))
static std::size_t {vector}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    std::size_t selected = 0;
    std::size_t i = 0;
    for (; n - i >= 8; i += 8) {{
        const __m512i lhs = _mm512_loadu_si512(static_cast<const void*>(current + i));
        const __m512i rhs = _mm512_loadu_si512(static_cast<const void*>(baseline + i));
        selected += static_cast<std::size_t>(std::popcount(static_cast<unsigned>(_mm512_cmpneq_epi64_mask(lhs, rhs))));
    }}
    for (; i < n; ++i) selected += current[i] != baseline[i];
    {_capacity_limit(contract)}
    std::size_t output = 0;
    i = 0;
    for (; n - i >= 8 && output < limit; i += 8) {{
        const __m512i lhs = _mm512_loadu_si512(static_cast<const void*>(current + i));
        const __m512i rhs = _mm512_loadu_si512(static_cast<const void*>(baseline + i));
        const __mmask8 mask = _mm512_cmpneq_epi64_mask(lhs, rhs);
        unsigned bits = static_cast<unsigned>(mask);
        const std::size_t remaining = limit - output;
        while (static_cast<std::size_t>(std::popcount(bits)) > remaining)
            bits &= ~(1U << (31U - static_cast<unsigned>(std::countl_zero(bits))));
        const __mmask8 store_mask = static_cast<__mmask8>(bits);
        {store_values}
        while (bits != 0 && output < limit) {{
            const std::size_t lane = static_cast<std::size_t>(std::countr_zero(bits));
            {write_index}
            ++output;
            bits &= bits - 1;
        }}
    }}
    for (; i < n && output < limit; ++i) {{
        if (current[i] == baseline[i]) continue;
        {tail_write}
        ++output;
    }}
    return output;
}}

extern "C" std::size_t {function}(
    std::uint32_t* out_indices, std::uint64_t* out_values, std::size_t capacity,
    const std::uint64_t* current, const std::uint64_t* baseline, std::size_t n) noexcept {{
    if (__builtin_cpu_supports("avx512f"))
        return {vector}(out_indices, out_values, capacity, current, baseline, n);
    return {scalar}(out_indices, out_values, capacity, current, baseline, n);
}}
"""


def _codec(contract: BoundedDataflowContract, realization: str, function: str) -> str:
    if len(contract.field_widths) != 3:
        raise ValueError("v1 C++ codec emitter requires exactly three fields")
    first, second, third = contract.field_widths
    shifts = (0, first, first + second)
    masks = tuple((1 << width) - 1 if width < 64 else (1 << 64) - 1 for width in contract.field_widths)
    swap = "word = __builtin_bswap64(word);" if contract.byte_order == "big" else ""
    expression = (
        f"(static_cast<std::uint64_t>(field0) & UINT64_C(0x{masks[0]:X}))"
        f" | ((static_cast<std::uint64_t>(field1) & UINT64_C(0x{masks[1]:X})) << {shifts[1]})"
        f" | ((static_cast<std::uint64_t>(field2) & UINT64_C(0x{masks[2]:X})) << {shifts[2]})"
    )
    return f"""
extern "C" std::uint64_t {function}(
    std::uint16_t field0, std::uint16_t field1, std::uint32_t field2) noexcept {{
    std::uint64_t word = {expression};
    {swap}
    return word;
}}
"""


def _state_delta(contract: BoundedDataflowContract, realization: str, function: str) -> str:
    mask = realization == "mask-transactional-delta"
    emit_loop = """
    for (std::size_t base = 0; base < n; base += 64) {
        std::uint64_t mask = 0;
        const std::size_t lanes = std::min<std::size_t>(64, n - base);
        for (std::size_t lane = 0; lane < lanes; ++lane)
            mask |= static_cast<std::uint64_t>(current[base + lane] != baseline[base + lane]) << lane;
        while (mask != 0) {
            const std::size_t lane = static_cast<std::size_t>(std::countr_zero(mask));
            const std::size_t i = base + lane;
            out_indices[output] = static_cast<std::uint32_t>(i);
            out_values[output] = current[i];
            next[i] = current[i];
            ++output;
            mask &= mask - 1;
        }
    }
""" if mask else """
    for (std::size_t i = 0; i < n; ++i) {
        if (current[i] == baseline[i]) continue;
        out_indices[output] = static_cast<std::uint32_t>(i);
        out_values[output] = current[i];
        next[i] = current[i];
        ++output;
    }
"""
    initialize = "" if realization == "staged-delta" else "std::memcpy(next, baseline, n * sizeof(std::uint64_t));"
    finalize = "std::memcpy(next, current, n * sizeof(std::uint64_t));" if realization == "staged-delta" else ""
    next_write = "" if realization == "staged-delta" else "next[i] = current[i];"
    emit_loop = emit_loop.replace("next[i] = current[i];", next_write)
    return f"""
extern "C" std::size_t {function}(
    std::uint64_t* next, std::uint32_t* out_indices, std::uint64_t* out_values,
    std::size_t capacity, const std::uint64_t* current,
    const std::uint64_t* baseline, std::size_t n) noexcept {{
    std::size_t selected = 0;
    for (std::size_t i = 0; i < n; ++i) selected += current[i] != baseline[i];
    if (selected > capacity) return std::numeric_limits<std::size_t>::max();
    {initialize}
    std::size_t output = 0;
    {emit_loop}
    {finalize}
    return output;
}}
"""


def _aos(realization: str, function: str) -> str:
    record = f"{function}_record"
    stats = f"{function}_stats"
    if realization == "repeated-projection-scans":
        body = """
    for (std::size_t i = 0; i < n; ++i) result.count += records[i].kind == kind && (records[i].flags & 1U) == 0U;
    for (std::size_t i = 0; i < n; ++i) if (records[i].kind == kind && (records[i].flags & 1U) == 0U) result.bytes += records[i].bytes;
    for (std::size_t i = 0; i < n; ++i) if (records[i].kind == kind && (records[i].flags & 1U) == 0U) result.flagged += (records[i].flags >> 1U) & 1U;
"""
    elif realization == "fused-aos-reductions":
        body = """
    for (std::size_t i = 0; i < n; ++i) {
        const bool selected = records[i].kind == kind && (records[i].flags & 1U) == 0U;
        result.count += selected;
        result.bytes += selected ? records[i].bytes : 0U;
        result.flagged += selected ? ((records[i].flags >> 1U) & 1U) : 0U;
    }
"""
    else:
        body = """
    for (std::size_t base = 0; base < n; base += 32) {
        const std::size_t end = std::min<std::size_t>(n, base + 32);
        for (std::size_t i = base; i < end; ++i) {
            const bool selected = records[i].kind == kind && (records[i].flags & 1U) == 0U;
            result.count += selected;
            result.bytes += selected ? records[i].bytes : 0U;
            result.flagged += selected ? ((records[i].flags >> 1U) & 1U) : 0U;
        }
    }
"""
    return f"""
struct {record} {{ std::uint32_t kind; std::uint32_t flags; std::uint64_t bytes; }};
struct {stats} {{ std::uint64_t count; std::uint64_t bytes; std::uint64_t flagged; }};
extern "C" {stats} {function}(const {record}* records, std::size_t n, std::uint32_t kind) noexcept {{
    {stats} result{{}};
    {body}
    return result;
}}
"""


def _block(realization: str, function: str) -> str:
    suffix = function.replace("-", "_")
    pixel = f"{suffix}_pixel"
    if realization == "packed-lane-4x4-block":
        load = """
        std::uint32_t word;
        std::memcpy(&word, pixels + i, sizeof(word));
        const std::uint8_t r = static_cast<std::uint8_t>(word);
        const std::uint8_t g = static_cast<std::uint8_t>(word >> 8U);
        const std::uint8_t b = static_cast<std::uint8_t>(word >> 16U);
"""
    else:
        load = """
        const std::uint8_t r = pixels[i].r;
        const std::uint8_t g = pixels[i].g;
        const std::uint8_t b = pixels[i].b;
"""
    return f"""
struct {pixel} {{ std::uint8_t r, g, b, a; }};
static std::uint16_t {suffix}_rgb565(std::uint8_t r, std::uint8_t g, std::uint8_t b) noexcept {{
    return static_cast<std::uint16_t>(((r >> 3U) << 11U) | ((g >> 2U) << 5U) | (b >> 3U));
}}
static {pixel} {suffix}_decode565(std::uint16_t value) noexcept {{
    const std::uint8_t r5 = static_cast<std::uint8_t>((value >> 11U) & 31U);
    const std::uint8_t g6 = static_cast<std::uint8_t>((value >> 5U) & 63U);
    const std::uint8_t b5 = static_cast<std::uint8_t>(value & 31U);
    return {{static_cast<std::uint8_t>((r5 << 3U) | (r5 >> 2U)), static_cast<std::uint8_t>((g6 << 2U) | (g6 >> 4U)), static_cast<std::uint8_t>((b5 << 3U) | (b5 >> 2U)), 255U}};
}}
extern "C" std::uint64_t {function}(const {pixel}* pixels) noexcept {{
    std::uint8_t lr = 255U, lg = 255U, lb = 255U, hr = 0U, hg = 0U, hb = 0U;
    for (std::size_t i = 0; i < 16; ++i) {{
        {load}
        lr = std::min(lr, r); lg = std::min(lg, g); lb = std::min(lb, b);
        hr = std::max(hr, r); hg = std::max(hg, g); hb = std::max(hb, b);
    }}
    const std::uint16_t low = {suffix}_rgb565(lr, lg, lb);
    const std::uint16_t high = {suffix}_rgb565(hr, hg, hb);
    const {pixel} p0 = {suffix}_decode565(low), p1 = {suffix}_decode565(high);
    const std::array<{pixel}, 4> palette{{p0, p1,
        {pixel}{{static_cast<std::uint8_t>((2U * p0.r + p1.r) / 3U), static_cast<std::uint8_t>((2U * p0.g + p1.g) / 3U), static_cast<std::uint8_t>((2U * p0.b + p1.b) / 3U), 255U}},
        {pixel}{{static_cast<std::uint8_t>((p0.r + 2U * p1.r) / 3U), static_cast<std::uint8_t>((p0.g + 2U * p1.g) / 3U), static_cast<std::uint8_t>((p0.b + 2U * p1.b) / 3U), 255U}}}};
    std::uint32_t indices = 0;
    for (std::size_t i = 0; i < 16; ++i) {{
        std::uint32_t best = 0, best_error = std::numeric_limits<std::uint32_t>::max();
        for (std::uint32_t p = 0; p < 4; ++p) {{
            const int dr = static_cast<int>(pixels[i].r) - palette[p].r;
            const int dg = static_cast<int>(pixels[i].g) - palette[p].g;
            const int db = static_cast<int>(pixels[i].b) - palette[p].b;
            const std::uint32_t error = static_cast<std::uint32_t>(dr * dr + dg * dg + db * db);
            if (error < best_error) {{ best_error = error; best = p; }}
        }}
        indices |= best << (2U * i);
    }}
    return static_cast<std::uint64_t>(low) | (static_cast<std::uint64_t>(high) << 16U) | (static_cast<std::uint64_t>(indices) << 32U);
}}
"""


def emit_dataflow_cpp(
    contract: BoundedDataflowContract,
    derivation: DataflowDerivation,
    function: str = "dataflow_candidate",
    grammar: BoundedDataflowGrammar | None = None,
) -> DataflowCandidate:
    grammar = grammar or load_bounded_dataflow_grammar()
    terminal = grammar.terminals.get(derivation.target)
    if terminal is None or terminal.get("family") != contract.family:
        raise ValueError("derivation terminal does not match the dataflow contract")
    realization = derivation.target
    if contract.family == "predicate-stable-compaction":
        body = (
            _compaction_scalar(contract, function) if realization == "scalar-two-pass"
            else _compaction_fused(contract, function) if realization == "fused-stable"
            else _compaction_mask(contract, function) if realization == "mask-prefix-stable"
            else _compaction_avx2(contract, function) if realization == "guarded-avx2-compaction"
            else _compaction_avx512(contract, function)
        )
    elif contract.family == "fixed-width-codec":
        body = _codec(contract, realization, function)
    elif contract.family == "stateful-delta-transducer":
        body = _state_delta(contract, realization, function)
    elif contract.family == "aos-fused-multi-reduction":
        body = _aos(realization, function)
    else:
        body = _block(realization, function)
    source = _preamble() + "\n" + body.strip() + "\n"
    graph = build_bounded_dataflow_graph(contract, realization, source_language="cpp", function_identity=function)
    obligations = (
        obligation("dataflow.cpp.borrowed-input", "ownership", "input spans remain alive and readable", scope="generated-function", proof_method="typed-adapter-contract", language="cpp", native_construct="pointer-plus-extent"),
        obligation("dataflow.cpp.caller-output", "ownership", "output storage is caller-owned and capacity checked", scope="generated-function", proof_method="typed-adapter-contract", language="cpp", native_construct="pointer-plus-capacity"),
        obligation("dataflow.cpp.noexcept", "exception", "generated bounded kernel cannot throw", scope="generated-function", proof_method="native-compile-and-effect-check", language="cpp", native_construct="noexcept"),
    )
    return DataflowCandidate(
        f"{contract.family}:{realization}", "cpp", function, contract.family, realization,
        source, hashlib.sha256(source.encode()).hexdigest(), derivation.derivation_hash,
        graph.graph_hash, ("-std=c++20", "-O3", "-march=native", "-Wall", "-Wextra"), obligations,
    )


def _differential_harness(contract: BoundedDataflowContract, candidate: DataflowCandidate) -> str:
    function = candidate.function
    if contract.family == "predicate-stable-compaction":
        check_index = "if (got_indices[i] != expected_indices[i]) return 12;" if contract.output_mode != "value-only" else ""
        check_value = "if (got_values[i] != expected_values[i]) return 13;" if contract.output_mode != "index-only" else ""
        failure = """
            if (got != std::numeric_limits<std::size_t>::max()) return 8;
            for (std::size_t i = 0; i < n + 1; ++i) if (got_indices[i] != 0xDEADBEEFU || got_values[i] != UINT64_C(0xBAD0BAD0BAD0BAD0)) return 9;
            continue;
""" if contract.capacity_policy == "fail-unchanged" else ""
        return f"""
int main() {{
    std::uint64_t seed = UINT64_C(0x9E3779B97F4A7C15);
    for (std::size_t n = 0; n <= 96; ++n) {{
        std::array<std::uint64_t, 97> current{{}}, baseline{{}};
        for (std::size_t i = 0; i < n; ++i) {{ seed ^= seed << 7; seed ^= seed >> 9; current[i] = seed; baseline[i] = (i % 3 == 0) ? seed : seed ^ (UINT64_C(1) << (i % 63)); }}
        std::array<std::uint32_t, 97> expected_indices{{}};
        std::array<std::uint64_t, 97> expected_values{{}};
        std::size_t selected = 0;
        for (std::size_t i = 0; i < n; ++i) if (current[i] != baseline[i]) {{ expected_indices[selected] = static_cast<std::uint32_t>(i); expected_values[selected++] = current[i]; }}
        for (std::size_t capacity = 0; capacity <= n + 1; ++capacity) {{
            std::array<std::uint32_t, 97> got_indices; got_indices.fill(0xDEADBEEFU);
            std::array<std::uint64_t, 97> got_values; got_values.fill(UINT64_C(0xBAD0BAD0BAD0BAD0));
            const std::size_t got = {function}(got_indices.data(), got_values.data(), capacity, current.data(), baseline.data(), n);
            if (selected > capacity) {{ {failure} }}
            const std::size_t expected = std::min(selected, capacity);
            if (got != expected) return 10;
            for (std::size_t i = 0; i < expected; ++i) {{ {check_index} {check_value} }}
        }}
    }}
    return 0;
}}
"""
    if contract.family == "fixed-width-codec":
        first, second, third = contract.field_widths
        masks = tuple((1 << width) - 1 for width in contract.field_widths)
        swap = "expected = __builtin_bswap64(expected);" if contract.byte_order == "big" else ""
        return f"""
int main() {{
    std::uint64_t seed = 17;
    for (unsigned i = 0; i < 100000; ++i) {{
        seed = seed * UINT64_C(6364136223846793005) + 1;
        const std::uint16_t a = static_cast<std::uint16_t>(seed), b = static_cast<std::uint16_t>(seed >> 16U);
        const std::uint32_t c = static_cast<std::uint32_t>(seed >> 32U);
        std::uint64_t expected = (static_cast<std::uint64_t>(a) & UINT64_C(0x{masks[0]:X}))
            | ((static_cast<std::uint64_t>(b) & UINT64_C(0x{masks[1]:X})) << {first})
            | ((static_cast<std::uint64_t>(c) & UINT64_C(0x{masks[2]:X})) << {first + second});
        {swap}
        if ({function}(a, b, c) != expected) return 20;
    }}
    return 0;
}}
"""
    if contract.family == "stateful-delta-transducer":
        return f"""
int main() {{
    std::array<std::uint64_t, 65> current{{}}, baseline{{}}, next{{}};
    std::array<std::uint32_t, 65> indices{{}}; std::array<std::uint64_t, 65> values{{}};
    for (std::size_t n = 0; n <= 64; ++n) {{
        std::size_t changed = 0;
        for (std::size_t i = 0; i < n; ++i) {{ baseline[i] = i * 17; current[i] = (i % 4 == 0) ? baseline[i] : baseline[i] + 3; changed += current[i] != baseline[i]; }}
        next.fill(UINT64_C(0xFEEDFACE)); indices.fill(0xFFFFFFFFU); values.fill(UINT64_C(0xBAD));
        const auto fail = {function}(next.data(), indices.data(), values.data(), changed ? changed - 1 : 0, current.data(), baseline.data(), n);
        if (changed && fail != std::numeric_limits<std::size_t>::max()) return 30;
        if (changed) for (std::size_t i = 0; i < n; ++i) if (next[i] != UINT64_C(0xFEEDFACE)) return 31;
        const auto got = {function}(next.data(), indices.data(), values.data(), changed, current.data(), baseline.data(), n);
        if (got != changed) return 32;
        for (std::size_t i = 0; i < n; ++i) if (next[i] != current[i]) return 33;
        for (std::size_t i = 0; i < changed; ++i) if (current[indices[i]] != values[i]) return 34;
    }}
    return 0;
}}
"""
    if contract.family == "aos-fused-multi-reduction":
        record = f"{function}_record"
        return f"""
int main() {{
    std::array<{record}, 257> records{{}};
    for (std::size_t n = 0; n <= 256; ++n) {{
        records[n] = {{static_cast<std::uint32_t>(n % 5), static_cast<std::uint32_t>(n % 7 == 0 ? 2 : 0), n * 13}};
        for (std::uint32_t kind = 0; kind < 5; ++kind) {{
            std::uint64_t count = 0, bytes = 0, flagged = 0;
            for (std::size_t i = 0; i <= n; ++i) if (records[i].kind == kind && (records[i].flags & 1U) == 0U) {{ ++count; bytes += records[i].bytes; flagged += (records[i].flags >> 1U) & 1U; }}
            const auto got = {function}(records.data(), n + 1, kind);
            if (got.count != count || got.bytes != bytes || got.flagged != flagged) return 40;
        }}
    }}
    return 0;
}}
"""
    pixel = f"{function}_pixel"
    return f"""
int main() {{
    std::array<{pixel}, 16> pixels{{}};
    for (unsigned trial = 0; trial < 1000; ++trial) {{
        for (unsigned i = 0; i < 16; ++i) pixels[i] = {{static_cast<std::uint8_t>(trial + i * 11), static_cast<std::uint8_t>(trial * 3 + i * 7), static_cast<std::uint8_t>(trial * 5 + i * 13), 255U}};
        std::uint8_t lr = 255U, lg = 255U, lb = 255U, hr = 0U, hg = 0U, hb = 0U;
        for (const auto& px : pixels) {{
            lr = std::min(lr, px.r); lg = std::min(lg, px.g); lb = std::min(lb, px.b);
            hr = std::max(hr, px.r); hg = std::max(hg, px.g); hb = std::max(hb, px.b);
        }}
        const auto pack565 = [](std::uint8_t r, std::uint8_t g, std::uint8_t b) {{
            return static_cast<std::uint16_t>(((r >> 3U) << 11U) | ((g >> 2U) << 5U) | (b >> 3U));
        }};
        const auto decode565 = [](std::uint16_t value) {{
            const std::uint8_t r5 = static_cast<std::uint8_t>((value >> 11U) & 31U);
            const std::uint8_t g6 = static_cast<std::uint8_t>((value >> 5U) & 63U);
            const std::uint8_t b5 = static_cast<std::uint8_t>(value & 31U);
            return {pixel}{{static_cast<std::uint8_t>((r5 << 3U) | (r5 >> 2U)), static_cast<std::uint8_t>((g6 << 2U) | (g6 >> 4U)), static_cast<std::uint8_t>((b5 << 3U) | (b5 >> 2U)), 255U}};
        }};
        const std::uint16_t low = pack565(lr, lg, lb), high = pack565(hr, hg, hb);
        const auto p0 = decode565(low), p1 = decode565(high);
        const std::array<{pixel}, 4> palette{{p0, p1,
            {pixel}{{static_cast<std::uint8_t>((2U * p0.r + p1.r) / 3U), static_cast<std::uint8_t>((2U * p0.g + p1.g) / 3U), static_cast<std::uint8_t>((2U * p0.b + p1.b) / 3U), 255U}},
            {pixel}{{static_cast<std::uint8_t>((p0.r + 2U * p1.r) / 3U), static_cast<std::uint8_t>((p0.g + 2U * p1.g) / 3U), static_cast<std::uint8_t>((p0.b + 2U * p1.b) / 3U), 255U}}}};
        std::uint32_t expected_indices = 0;
        for (unsigned i = 0; i < 16; ++i) {{
            std::uint32_t best = 0, best_error = std::numeric_limits<std::uint32_t>::max();
            for (std::uint32_t p = 0; p < 4; ++p) {{
                const int dr = static_cast<int>(pixels[i].r) - palette[p].r;
                const int dg = static_cast<int>(pixels[i].g) - palette[p].g;
                const int db = static_cast<int>(pixels[i].b) - palette[p].b;
                const auto error = static_cast<std::uint32_t>(dr * dr + dg * dg + db * db);
                if (error < best_error) {{ best_error = error; best = p; }}
            }}
            expected_indices |= best << (2U * i);
        }}
        const std::uint64_t expected = static_cast<std::uint64_t>(low)
            | (static_cast<std::uint64_t>(high) << 16U)
            | (static_cast<std::uint64_t>(expected_indices) << 32U);
        if ({function}(pixels.data()) != expected) return 50;
    }}
    return 0;
}}
"""


def run_dataflow_differential(
    contract: BoundedDataflowContract,
    candidate: DataflowCandidate,
    output_directory: Path,
) -> dict[str, Any]:
    compiler = shutil.which("clang++-20") or shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        return {"status": "UNAVAILABLE", "reason": "no C++20 compiler found"}
    output_directory.mkdir(parents=True, exist_ok=True)
    source = output_directory / "differential.cpp"
    binary = output_directory / "differential"
    source.write_text(candidate.source + "\n" + _differential_harness(contract, candidate))
    compiled = subprocess.run(
        [compiler, *candidate.compiler_flags, str(source), "-o", str(binary)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if compiled.returncode != 0:
        return {"status": "FAIL", "phase": "compile", "stderr": compiled.stderr[-4000:], "source": str(source)}
    executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    return {
        "status": "PASS" if executed.returncode == 0 else "FAIL",
        "phase": "execute",
        "returncode": executed.returncode,
        "stderr": executed.stderr[-4000:],
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "binary": str(binary),
    }
