#include <cstdint>

struct LargeResult {
    std::uint64_t first;
    std::uint64_t second;
    std::uint64_t third;
    std::uint64_t fourth;
};

LargeResult widen_result(std::uint64_t value) noexcept {
    return {value, value + 1U, value + 2U, value + 3U};
}
