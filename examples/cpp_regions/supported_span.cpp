#include <cstddef>
#include <span>

void transform(std::span<float> dst, std::span<const float> src) noexcept {
    const std::size_t n = src.size();
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = src[i] * 1.5f + 0.125f;
    }
}
