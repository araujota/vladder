#include <cstddef>
#include <span>

int first_positive(std::span<const int> values) noexcept {
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (values[index] > 0) {
            return static_cast<int>(index);
        }
    }
    return -1;
}
