#include <span>

void visit_values(std::span<const int> values, void (*callback)(int)) {
    for (const int value : values) {
        callback(value);
    }
}
