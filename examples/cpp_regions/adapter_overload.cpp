#include <cstddef>

void transform(float *dst, const float *src, std::size_t n) noexcept {
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = src[i];
    }
}

void transform(double *dst, const double *src, std::size_t n) noexcept {
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = src[i];
    }
}
