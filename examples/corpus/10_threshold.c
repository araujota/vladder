#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        dst[i] = src[i] > 0.25f ? 1.0f : 0.0f;
    }
}
