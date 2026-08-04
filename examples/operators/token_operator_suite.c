#include <math.h>
#include <stddef.h>
#include <stdint.h>

void rope_qk(const float *q, const float *k, const float *cos_values, const float *sin_values,
             float *q_out, float *k_out, size_t pairs) {
    for (size_t p = 0; p < pairs; ++p) {
        size_t i = 2 * p;
        float c = cos_values[p], s = sin_values[p];
        q_out[i] = q[i] * c - q[i + 1] * s;
        q_out[i + 1] = q[i] * s + q[i + 1] * c;
        k_out[i] = k[i] * c - k[i + 1] * s;
        k_out[i + 1] = k[i] * s + k[i + 1] * c;
    }
}

void quantized_gemv_epilogue(const int8_t *weights, const float *scales, const float *x,
                             float *output, size_t n, size_t block, float bias, float gate) {
    float sum = 0.0f;
    for (size_t i = 0; i < n; ++i) sum += (float)weights[i] * scales[i / block] * x[i];
    float value = sum + bias;
    *output = value / (1.0f + expf(-value)) * gate;
}

void decode_attention_online(const float *q, const float *keys, const float *values,
                             float *output, size_t context, size_t dimension, float scale) {
    for (size_t d = 0; d < dimension; ++d) output[d] = 0.0f;
    float maximum = -INFINITY, denominator = 0.0f;
    for (size_t j = 0; j < context; ++j) {
        float score = 0.0f;
        for (size_t d = 0; d < dimension; ++d) score += q[d] * keys[j * dimension + d];
        score *= scale;
        float next_maximum = fmaxf(maximum, score);
        float old_weight = isinf(maximum) ? 0.0f : expf(maximum - next_maximum);
        float new_weight = expf(score - next_maximum);
        denominator = denominator * old_weight + new_weight;
        for (size_t d = 0; d < dimension; ++d) output[d] = output[d] * old_weight + values[j * dimension + d] * new_weight;
        maximum = next_maximum;
    }
    for (size_t d = 0; d < dimension; ++d) output[d] /= denominator;
}

void logit_penalty_greedy(const float *logits, const uint8_t *repeated, float *adjusted,
                          int32_t *token_out, size_t vocabulary, float penalty, float temperature) {
    float best = -INFINITY;
    int32_t token = 0;
    for (size_t i = 0; i < vocabulary; ++i) {
        float value = logits[i];
        if (repeated[i]) value = value > 0.0f ? value / penalty : value * penalty;
        value /= temperature;
        adjusted[i] = value;
        if (value > best) { best = value; token = (int32_t)i; }
    }
    *token_out = token;
}
