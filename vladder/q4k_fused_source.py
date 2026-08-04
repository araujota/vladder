from __future__ import annotations


FUSED_Q4K_SIBLING_SOURCE = r'''
#define GGML_COMMON_DECL_CPP
#include "ggml-common.h"
#include "repack.h"
#include <immintrin.h>
#include <cassert>
#include <cstdint>
#include <cstring>

#define GGML_F32Cx8_LOAD(x) _mm256_cvtph_ps(_mm_loadu_si128((const __m128i *)(x)))
#define GGML_F32Cx8_REARRANGE_LOAD(x, mask) _mm256_cvtph_ps(_mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(x)), mask))

// This is the native Q4_K sub-block computation with only the Q8_K loads
// lifted into the caller so the same activation vectors serve both siblings.
static inline __attribute__((always_inline)) void vladder_q4k_subblock(
    const block_q4_Kx8 & w, int sb,
    __m256i lhs00, __m256i lhs01, __m256i lhs10, __m256i lhs11,
    __m256i q8s_sb, __m128i scalemask, __m256i m4b,
    __m256i & block_acc, __m256i & minimum_acc) {
    static const uint32_t kmask1 = 0x3f3f3f3f;
    static const uint32_t kmask2 = 0x0f0f0f0f;
    static const uint32_t kmask3 = 0x03030303;

    const __m256i raw00 = _mm256_loadu_si256((const __m256i *)(w.qs + sb*256));
    const __m256i raw40 = _mm256_loadu_si256((const __m256i *)(w.qs + 32 + sb*256));
    const __m256i raw01 = _mm256_loadu_si256((const __m256i *)(w.qs + 64 + sb*256));
    const __m256i raw41 = _mm256_loadu_si256((const __m256i *)(w.qs + 96 + sb*256));
    const __m256i raw02 = _mm256_loadu_si256((const __m256i *)(w.qs + 128 + sb*256));
    const __m256i raw42 = _mm256_loadu_si256((const __m256i *)(w.qs + 160 + sb*256));
    const __m256i raw03 = _mm256_loadu_si256((const __m256i *)(w.qs + 192 + sb*256));
    const __m256i raw43 = _mm256_loadu_si256((const __m256i *)(w.qs + 224 + sb*256));

    const __m256i r000 = _mm256_and_si256(raw00, m4b);
    const __m256i r400 = _mm256_and_si256(raw40, m4b);
    const __m256i r001 = _mm256_and_si256(raw01, m4b);
    const __m256i r401 = _mm256_and_si256(raw41, m4b);
    const __m256i r002 = _mm256_and_si256(raw02, m4b);
    const __m256i r402 = _mm256_and_si256(raw42, m4b);
    const __m256i r003 = _mm256_and_si256(raw03, m4b);
    const __m256i r403 = _mm256_and_si256(raw43, m4b);
    const __m256i r100 = _mm256_and_si256(_mm256_srli_epi16(raw00, 4), m4b);
    const __m256i r500 = _mm256_and_si256(_mm256_srli_epi16(raw40, 4), m4b);
    const __m256i r101 = _mm256_and_si256(_mm256_srli_epi16(raw01, 4), m4b);
    const __m256i r501 = _mm256_and_si256(_mm256_srli_epi16(raw41, 4), m4b);
    const __m256i r102 = _mm256_and_si256(_mm256_srli_epi16(raw02, 4), m4b);
    const __m256i r502 = _mm256_and_si256(_mm256_srli_epi16(raw42, 4), m4b);
    const __m256i r103 = _mm256_and_si256(_mm256_srli_epi16(raw03, 4), m4b);
    const __m256i r503 = _mm256_and_si256(_mm256_srli_epi16(raw43, 4), m4b);

    uint32_t u0[4], u1[4];
    memcpy(u0, w.scales + 24*sb, 12);
    u0[3] = ((u0[2] >> 4) & kmask2) | (((u0[1] >> 6) & kmask3) << 4);
    const uint32_t aux0 = u0[1] & kmask1;
    u0[1] = (u0[2] & kmask2) | (((u0[0] >> 6) & kmask3) << 4);
    u0[2] = aux0; u0[0] &= kmask1;
    memcpy(u1, w.scales + 12 + 24*sb, 12);
    u1[3] = ((u1[2] >> 4) & kmask2) | (((u1[1] >> 6) & kmask3) << 4);
    const uint32_t aux1 = u1[1] & kmask1;
    u1[1] = (u1[2] & kmask2) | (((u1[0] >> 6) & kmask3) << 4);
    u1[2] = aux1; u1[0] &= kmask1;

    const __m128i ms0 = _mm_set_epi32(u0[3], u0[2], u0[1], u0[0]);
    const __m128i ms1 = _mm_set_epi32(u1[3], u1[2], u1[1], u1[0]);
    const __m256i scales0 = _mm256_cvtepu8_epi16(_mm_shuffle_epi8(ms0, scalemask));
    const __m256i scales1 = _mm256_cvtepu8_epi16(_mm_shuffle_epi8(ms1, scalemask));
    const __m256i mins = _mm256_cvtepu8_epi16(
        _mm_unpacklo_epi8(_mm_shuffle_epi32(ms0, 78), _mm_shuffle_epi32(ms1, 78)));

    __m256i a0 = _mm256_setzero_si256();
    __m256i a1 = _mm256_setzero_si256();
#define ST_DOT_PAIR(acc, lo, hi, lhs, s0, s1) do { \
    acc = _mm256_add_epi16(acc, _mm256_maddubs_epi16( \
        _mm256_blend_epi32(lo, _mm256_shuffle_epi32(hi, 177), 170), _mm256_shuffle_epi32(lhs, s0))); \
    acc = _mm256_add_epi16(acc, _mm256_maddubs_epi16( \
        _mm256_blend_epi32(_mm256_shuffle_epi32(lo, 177), hi, 170), _mm256_shuffle_epi32(lhs, s1))); \
} while (0)
    ST_DOT_PAIR(a0, r000, r400, lhs00, 0, 85);
    ST_DOT_PAIR(a0, r001, r401, lhs00, 170, 255);
    ST_DOT_PAIR(a0, r002, r402, lhs01, 0, 85);
    ST_DOT_PAIR(a0, r003, r403, lhs01, 170, 255);
    a0 = _mm256_madd_epi16(a0, scales0);
    ST_DOT_PAIR(a1, r100, r500, lhs10, 0, 85);
    ST_DOT_PAIR(a1, r101, r501, lhs10, 170, 255);
    ST_DOT_PAIR(a1, r102, r502, lhs11, 0, 85);
    ST_DOT_PAIR(a1, r103, r503, lhs11, 170, 255);
    a1 = _mm256_madd_epi16(a1, scales1);
#undef ST_DOT_PAIR
    block_acc = _mm256_add_epi32(block_acc, _mm256_add_epi32(a0, a1));
    minimum_acc = _mm256_add_epi32(minimum_acc, _mm256_madd_epi16(q8s_sb, mins));
}

extern "C" void vladder_fused_gemv_q4_K_8x8_q8_K(
    int n, float * gate_out, float * up_out,
    const void * gate_weights, const void * up_weights,
    const void * activation, int nr, int nc) {
    assert(n % QK_K == 0 && nc % 8 == 0);
    const int64_t nb = n / QK_K;
    const auto * gate_start = (const block_q4_Kx8 *)gate_weights;
    const auto * up_start = (const block_q4_Kx8 *)up_weights;
    const auto * activation_start = (const block_q8_K *)activation;
    const __m128i delta_mask = _mm_set_epi8(15,14,7,6,13,12,5,4,11,10,3,2,9,8,1,0);
    const __m128i scale_mask = _mm_set_epi8(7,7,3,3,6,6,2,2,5,5,1,1,4,4,0,0);
    const __m256i final_mask = _mm256_set_epi32(7,5,3,1,6,4,2,0);
    const __m256i nibble_mask = _mm256_set1_epi8(0x0f);

    for (int64_t y = 0; y < nr; ++y) {
        const block_q8_K * a = activation_start + y*nb;
        for (int64_t x = 0; x < nc/8; ++x) {
            const block_q4_Kx8 * gate = gate_start + x*nb;
            const block_q4_Kx8 * up = up_start + x*nb;
            __m256 gate_acc = _mm256_setzero_ps(), gate_min = _mm256_setzero_ps();
            __m256 up_acc = _mm256_setzero_ps(), up_min = _mm256_setzero_ps();
            for (int64_t b = 0; b < nb; ++b) {
                const __m256 row_scale = _mm256_set1_ps(a[b].d);
                const __m256 gate_scale = GGML_F32Cx8_REARRANGE_LOAD(gate[b].d, delta_mask);
                const __m256 gate_dmin = GGML_F32Cx8_LOAD(gate[b].dmin);
                const __m256 up_scale = GGML_F32Cx8_REARRANGE_LOAD(up[b].d, delta_mask);
                const __m256 up_dmin = GGML_F32Cx8_LOAD(up[b].dmin);
                __m256i gate_iacc = _mm256_setzero_si256(), gate_iacc_min = _mm256_setzero_si256();
                __m256i up_iacc = _mm256_setzero_si256(), up_iacc_min = _mm256_setzero_si256();
                const __m256i sums = _mm256_loadu_si256((const __m256i *)a[b].bsums);
                __m256i q8s = _mm256_castsi128_si256(
                    _mm_hadd_epi16(_mm256_castsi256_si128(sums), _mm256_extracti128_si256(sums, 1)));
                q8s = _mm256_permute2f128_si256(q8s, q8s, 0);
                for (int sb = 0; sb < QK_K/64; ++sb) {
                    __m256i lhs00 = _mm256_castsi128_si256(_mm_loadu_si128((const __m128i *)(a[b].qs + sb*64)));
                    __m256i lhs01 = _mm256_castsi128_si256(_mm_loadu_si128((const __m128i *)(a[b].qs + 16 + sb*64)));
                    __m256i lhs10 = _mm256_castsi128_si256(_mm_loadu_si128((const __m128i *)(a[b].qs + 32 + sb*64)));
                    __m256i lhs11 = _mm256_castsi128_si256(_mm_loadu_si128((const __m128i *)(a[b].qs + 48 + sb*64)));
                    lhs00 = _mm256_permute2f128_si256(lhs00, lhs00, 0);
                    lhs01 = _mm256_permute2f128_si256(lhs01, lhs01, 0);
                    lhs10 = _mm256_permute2f128_si256(lhs10, lhs10, 0);
                    lhs11 = _mm256_permute2f128_si256(lhs11, lhs11, 0);
                    const __m256i q8s_sb = _mm256_shuffle_epi32(q8s, 0);
                    vladder_q4k_subblock(gate[b], sb, lhs00, lhs01, lhs10, lhs11,
                                             q8s_sb, scale_mask, nibble_mask, gate_iacc, gate_iacc_min);
                    vladder_q4k_subblock(up[b], sb, lhs00, lhs01, lhs10, lhs11,
                                             q8s_sb, scale_mask, nibble_mask, up_iacc, up_iacc_min);
                    q8s = _mm256_bsrli_epi128(q8s, 4);
                }
                gate_acc = _mm256_fmadd_ps(_mm256_cvtepi32_ps(gate_iacc), _mm256_mul_ps(gate_scale, row_scale), gate_acc);
                gate_min = _mm256_fmadd_ps(_mm256_cvtepi32_ps(gate_iacc_min), _mm256_mul_ps(gate_dmin, row_scale), gate_min);
                up_acc = _mm256_fmadd_ps(_mm256_cvtepi32_ps(up_iacc), _mm256_mul_ps(up_scale, row_scale), up_acc);
                up_min = _mm256_fmadd_ps(_mm256_cvtepi32_ps(up_iacc_min), _mm256_mul_ps(up_dmin, row_scale), up_min);
            }
            gate_acc = _mm256_permutevar8x32_ps(gate_acc, final_mask);
            up_acc = _mm256_permutevar8x32_ps(up_acc, final_mask);
            _mm256_storeu_ps(gate_out + y*nr + x*8, _mm256_sub_ps(gate_acc, gate_min));
            _mm256_storeu_ps(up_out + y*nr + x*8, _mm256_sub_ps(up_acc, up_min));
        }
    }
}
'''
