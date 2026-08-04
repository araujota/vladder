#include <cstddef>
#include <vector>

void transform(std::vector<float> &dst, const std::vector<float> &src) noexcept {
    const std::size_t n = src.size();
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = src[i] * 0.5f - 0.25f;
    }
}
