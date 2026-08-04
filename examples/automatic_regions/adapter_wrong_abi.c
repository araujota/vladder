#include <stddef.h>

void transform(float *dst, const float *lhs, const float *rhs, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        dst[i] = lhs[i] + rhs[i];
    }
}
