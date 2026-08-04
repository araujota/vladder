#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        float x = src[i];
        dst[i] = ((0.25f * x + 0.5f) * x - 1.0f) * x + 2.0f;
    }
}
