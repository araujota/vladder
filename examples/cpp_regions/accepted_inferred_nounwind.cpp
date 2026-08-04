#include <cstddef>
#include <cstdint>
#include <span>

std::uint32_t byte_checksum(std::span<const std::byte> bytes) {
    std::uint32_t result = 2166136261U;
    for (const std::byte value : bytes) {
        result ^= static_cast<std::uint8_t>(value);
        result *= 16777619U;
    }
    return result;
}
