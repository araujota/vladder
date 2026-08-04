#include <stddef.h>

void transform(float *dst, const float *src, size_t n) {
    if (n == 0) {
        return;
    }
    float max_value = src[0];
    for (size_t i = 0; i < n; ++i) {
        if (src[i] > max_value) {
            max_value = src[i];
        }
        dst[i] = max_value;
    }
}
