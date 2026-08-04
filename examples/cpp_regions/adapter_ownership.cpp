#include <cstddef>
#include <memory>
#include <span>

void transform(std::span<float> dst, std::span<const float> src) noexcept {
    auto temporary = std::make_unique<float[]>(src.size());
    for (std::size_t i = 0; i < src.size(); ++i) {
        temporary[i] = src[i];
        dst[i] = temporary[i];
    }
}
