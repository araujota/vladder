#include <immintrin.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

size_t c_scalar_count(const uint8_t *data, size_t n, uint8_t needle) {
    size_t count = 0;
    for (size_t i = 0; i < n; ++i) {
        count += data[i] == needle;
    }
    return count;
}

static uint64_t bytewise_equal(uint64_t lhs, uint64_t rhs) {
    const uint64_t lo = UINT64_C(0x0101010101010101);
    const uint64_t hi = UINT64_C(0x8080808080808080);
    const uint64_t x = lhs ^ rhs;
    return ~((((x & ~hi) + ~hi) | x) >> 7) & lo;
}

size_t c_word_count(const uint8_t *data, size_t n, uint8_t needle) {
    size_t count = 0;
    size_t i = 0;
    const uint64_t splat = UINT64_C(0x0101010101010101) * needle;
    for (; n - i >= 8; i += 8) {
        uint64_t word;
        memcpy(&word, data + i, sizeof(word));
        count += __builtin_popcountll(bytewise_equal(word, splat));
    }
    for (; i < n; ++i) count += data[i] == needle;
    return count;
}

__attribute__((target("avx2")))
size_t c_avx2_count(const uint8_t *data, size_t n, uint8_t needle) {
    size_t count = 0;
    size_t i = 0;
    const __m256i needles = _mm256_set1_epi8((char)needle);
    for (; n - i >= 32; i += 32) {
        const __m256i values = _mm256_loadu_si256((const __m256i *)(const void *)(data + i));
        const __m256i matches = _mm256_cmpeq_epi8(values, needles);
        count += __builtin_popcount((unsigned)_mm256_movemask_epi8(matches));
    }
    for (; i < n; ++i) count += data[i] == needle;
    return count;
}
