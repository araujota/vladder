#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        if (i == 0 || i + 1 >= n) {
            dst[i] = src[i];
        } else {
            dst[i] = src[i - 1] * 0.25f + src[i] * 0.5f + src[i + 1] * 0.25f;
        }
    }
}
