#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

std::vector<std::uint32_t> copy_words(std::span<const std::uint32_t> source) {
    std::vector<std::uint32_t> result(source.size());
    for (std::size_t index = 0; index < source.size(); ++index) {
        result[index] = source[index];
    }
    return result;
}
