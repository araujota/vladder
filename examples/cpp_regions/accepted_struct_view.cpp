#include <cstddef>
#include <cstdint>
#include <span>

struct CounterRow {
    std::uint32_t count;
    std::uint32_t weight;
};

std::uint64_t weighted_total(std::span<const CounterRow> rows) noexcept {
    std::uint64_t result = 0U;
    for (const CounterRow row : rows) {
        result += static_cast<std::uint64_t>(row.count) * row.weight;
    }
    return result;
}
