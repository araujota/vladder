#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    if (n == 0) {
        return;
    }
    dst[0] = src[0];
    for (size_t i = 1; i + 1 < n; ++i) {
        dst[i] = src[i - 1] * 0.25f + src[i] * 0.5f + src[i + 1] * 0.25f;
    }
    if (n > 1) {
        dst[n - 1] = src[n - 1];
    }
}
