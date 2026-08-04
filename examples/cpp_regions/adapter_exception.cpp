#include <cstddef>
#include <span>
#include <stdexcept>

void transform(std::span<float> dst, std::span<const float> src) {
    if (dst.size() < src.size()) {
        throw std::length_error("destination too short");
    }
    for (std::size_t i = 0; i < src.size(); ++i) {
        dst[i] = src[i];
    }
}
