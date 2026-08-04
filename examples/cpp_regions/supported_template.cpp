#include <cstddef>
#include <span>

template <class T>
void transform(std::span<T> dst, std::span<const T> src) noexcept;

template <>
void transform<float>(std::span<float> dst, std::span<const float> src) noexcept {
    const std::size_t n = src.size();
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = src[i] + 1.0f;
    }
}
