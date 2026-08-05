#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

void collect_unchecked(
    std::span<const std::uint32_t> values,
    std::vector<std::uint32_t>& output) noexcept {
    for (const std::uint32_t value : values) {
        output.push_back(value);
    }
    if (output.capacity() - output.size() >= values.size()) {
        return;
    }
}
