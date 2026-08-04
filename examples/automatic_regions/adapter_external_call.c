#include <stddef.h>

static float adjust(float value) {
    return value * 2.0f;
}

void transform(float *dst, const float *src, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        dst[i] = adjust(src[i]);
    }
}
