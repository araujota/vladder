#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        if (src[i] == 0.0f) {
            continue;
        }
        dst[i] = src[i];
    }
}
