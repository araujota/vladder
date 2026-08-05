#include <cstddef>
#include <cstdint>
#include <span>

[[gnu::noinline]] static std::uint32_t mix_word(std::uint32_t value) noexcept {
    return (value ^ 0x9e3779b9U) * 0x85ebca6bU;
}

std::uint64_t mix_total(std::span<const std::uint32_t> values) noexcept {
    std::uint64_t total = 0;
    for (const std::uint32_t value : values) {
        total += mix_word(value);
    }
    return total;
}
