#include <cstdint>
#include <span>

struct RunningCounter {
    std::uint64_t total{0};

    void add(std::span<const std::uint32_t> values) noexcept {
        for (const std::uint32_t value : values) {
            total += value;
        }
    }
};

void exercise_counter(RunningCounter& counter, std::span<const std::uint32_t> values) {
    counter.add(values);
}
