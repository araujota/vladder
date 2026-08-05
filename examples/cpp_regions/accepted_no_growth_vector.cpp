#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

bool collect_changed(
    std::span<const std::uint32_t> current,
    std::span<const std::uint32_t> baseline,
    std::vector<std::uint32_t>& changed) noexcept {
    if (current.size() != baseline.size() ||
        changed.capacity() - changed.size() < current.size()) {
        return false;
    }
    for (std::size_t index = 0; index < current.size(); ++index) {
        if (current[index] != baseline[index]) {
            changed.push_back(static_cast<std::uint32_t>(index));
        }
    }
    return true;
}
