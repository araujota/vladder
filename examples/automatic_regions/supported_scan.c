#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    float sum = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        sum += src[i];
        dst[i] = sum;
    }
}
