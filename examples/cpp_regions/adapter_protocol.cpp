#include <cstddef>
#include <cstdint>
#include <span>

extern void submit_bytes(const std::byte*, std::size_t);

void send_packet(std::span<const std::byte> bytes) {
    submit_bytes(bytes.data(), bytes.size());
}
