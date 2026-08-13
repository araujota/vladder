#include <cstddef>

template <bool AddOne>
void transform(float* dst, const float* src, std::size_t n) noexcept {
    for (std::size_t i = 0; i < n; ++i) {
        dst[i] = AddOne ? src[i] + 1.0f : src[i];
    }
}

template void transform<true>(float*, const float*, std::size_t) noexcept;
template void transform<false>(float*, const float*, std::size_t) noexcept;
