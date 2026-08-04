#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        float x = src[i];
        float ax = x < 0.0f ? -x : x;
        dst[i] = x / (1.0f + ax);
    }
}
