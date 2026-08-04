#include <cstddef>
#include <span>

struct Processor {
    void transform(std::span<float> dst, std::span<const float> src) const noexcept {
        const std::size_t n = src.size();
        for (std::size_t i = 0; i < n; ++i) {
            dst[i] = src[i] > 0.0f ? src[i] : 0.0f;
        }
    }
};

void exercise(Processor &processor, std::span<float> dst, std::span<const float> src) {
    processor.transform(dst, src);
}
