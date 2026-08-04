#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    float y = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        y = y * 0.875f + src[i] * 0.125f;
        dst[i] = y;
    }
}
