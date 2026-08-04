#include <cstddef>
#include <span>

extern float external_adjust(float);

void transform(std::span<float> dst, std::span<const float> src) noexcept {
    for (std::size_t i = 0; i < src.size(); ++i) {
        dst[i] = external_adjust(src[i]);
    }
}
