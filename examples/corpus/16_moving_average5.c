#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        if (i < 2 || i + 2 >= n) {
            dst[i] = src[i];
        } else {
            dst[i] = (src[i - 2] + src[i - 1] + src[i] + src[i + 1] + src[i + 2]) * 0.2f;
        }
    }
}
