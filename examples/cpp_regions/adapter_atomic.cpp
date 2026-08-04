#include <atomic>
#include <cstddef>
#include <span>

std::atomic<unsigned> observations{0};

void transform(std::span<float> dst, std::span<const float> src) noexcept {
    for (std::size_t i = 0; i < src.size(); ++i) {
        dst[i] = src[i];
        observations.fetch_add(1, std::memory_order_relaxed);
    }
}
