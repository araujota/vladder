#include <cstddef>

using extent_t = std::size_t;

void transform(float* dst, const float* src, extent_t n) noexcept {
    for (extent_t i = 0; i < n; ++i) {
        dst[i] = src[i] + 1.0F;
    }
}
