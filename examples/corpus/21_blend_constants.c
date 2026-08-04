#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        float x = src[i];
        dst[i] = x < -0.5f ? 0.25f : 2.0f;
    }
}
