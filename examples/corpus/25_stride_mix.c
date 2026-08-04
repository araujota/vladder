#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    if (n == 0) {
        return;
    }
    for (size_t i = 0; i < n; ++i) {
        size_t j = (i * 17u) % n;
        dst[i] = src[j] * 0.75f + src[i] * 0.25f;
    }
}
