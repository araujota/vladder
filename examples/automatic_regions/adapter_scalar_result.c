#include <stddef.h>
#include <stdint.h>

uint32_t checksum_bytes(const uint8_t *data, size_t n) {
    uint32_t value = 0;
    for (size_t index = 0; index < n; ++index) {
        value += data[index];
    }
    return value;
}
