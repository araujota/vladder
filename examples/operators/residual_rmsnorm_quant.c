#include <math.h>
#include <stddef.h>
#include <stdint.h>

void residual_rmsnorm_quant(
    const float *x,
    const float *residual,
    const float *weight,
    float *scratch,
    float *y,
    int8_t *q,
    float *scale_out,
    size_t n,
    float epsilon) {
    for (size_t i = 0; i < n; ++i) {
        scratch[i] = x[i] + residual[i];
    }
    float sum_sq = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        sum_sq += scratch[i] * scratch[i];
    }
    float scale = 1.0f / sqrtf(sum_sq / (float)n + epsilon);
    *scale_out = scale;
    for (size_t i = 0; i < n; ++i) {
        float value = scratch[i] * scale * weight[i];
        y[i] = value;
        float scaled = value * 127.0f;
        int quantized = (int)scaled;
        if (quantized > 127) quantized = 127;
        if (quantized < -127) quantized = -127;
        q[i] = (int8_t)quantized;
    }
}
