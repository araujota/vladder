#include <cstddef>
#include <span>
#include <string_view>

struct StatusResult {
    int code;
    std::string_view message;
    std::byte value;
};

StatusResult first_byte(std::span<const std::byte> bytes) noexcept {
    if (bytes.empty()) {
        return {1, "empty input", std::byte{0}};
    }
    return {0, "", bytes.front()};
}
