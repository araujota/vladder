#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

extern bool nondet_bool(void);

int main(void) {
    enum { CAPACITY = 4, STEPS = 12 };
    uint64_t slots[CAPACITY] = {0};
    size_t producer = 0, consumer = 0;
    uint64_t next_value = 0;
    for (size_t step = 0; step < STEPS; ++step) {
        if (nondet_bool()) {
            if (producer - consumer < CAPACITY) {
                slots[producer & (CAPACITY - 1)] = next_value++;
                ++producer;
            }
        } else if (consumer != producer) {
            uint64_t value = slots[consumer & (CAPACITY - 1)];
            assert(value == consumer);
            ++consumer;
        }
        assert(consumer <= producer);
        assert(producer - consumer <= CAPACITY);
    }
}
