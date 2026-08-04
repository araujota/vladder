#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        float x = src[i];
        if (x < -0.1f) {
            dst[i] = x + 0.1f;
        } else if (x > 0.1f) {
            dst[i] = x - 0.1f;
        } else {
            dst[i] = 0.0f;
        }
    }
}
