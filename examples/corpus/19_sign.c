#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        float x = src[i];
        if (x > 0.0f) {
            dst[i] = 1.0f;
        } else if (x < 0.0f) {
            dst[i] = -1.0f;
        } else {
            dst[i] = 0.0f;
        }
    }
}
