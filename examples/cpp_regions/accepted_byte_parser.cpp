#include <cstddef>
#include <cstdint>
#include <span>

struct ParseWordResult {
    bool ok;
    std::uint32_t value;
};

static std::uint32_t read_be32(std::span<const std::byte> bytes) noexcept {
    return (static_cast<std::uint32_t>(bytes[0]) << 24U) |
           (static_cast<std::uint32_t>(bytes[1]) << 16U) |
           (static_cast<std::uint32_t>(bytes[2]) << 8U) |
           static_cast<std::uint32_t>(bytes[3]);
}

ParseWordResult parse_word(std::span<const std::byte> bytes) noexcept {
    if (bytes.size() < 4U) {
        return {false, 0U};
    }
    return {true, read_be32(bytes)};
}
