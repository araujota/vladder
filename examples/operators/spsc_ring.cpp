#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#ifdef VLADDER_STRESS_MAIN
#include <thread>
#endif

template <std::size_t Capacity>
class SPSCRing {
    static_assert(Capacity > 1 && (Capacity & (Capacity - 1)) == 0);
public:
    bool enqueue(std::uint64_t value) {
        const auto producer = producer_.load(std::memory_order_relaxed);
        if (producer - consumer_.load(std::memory_order_acquire) == Capacity) return false;
        slots_[producer & (Capacity - 1)] = value;
        producer_.store(producer + 1, std::memory_order_release);
        return true;
    }

    bool dequeue(std::uint64_t &value) {
        const auto consumer = consumer_.load(std::memory_order_relaxed);
        if (consumer == producer_.load(std::memory_order_acquire)) return false;
        value = slots_[consumer & (Capacity - 1)];
        consumer_.store(consumer + 1, std::memory_order_release);
        return true;
    }

private:
    alignas(64) std::array<std::uint64_t, Capacity> slots_{};
    alignas(64) std::atomic<std::size_t> producer_{0};
    alignas(64) std::atomic<std::size_t> consumer_{0};
};

extern "C" int spsc_stress(std::size_t rounds) {
    SPSCRing<8> ring;
    for (std::size_t i = 0; i < rounds; ++i) {
        if (!ring.enqueue(i)) return 1;
        std::uint64_t value = 0;
        if (!ring.dequeue(value) || value != i) return 2;
    }
    return 0;
}

#ifdef VLADDER_STRESS_MAIN
int main() {
    constexpr std::size_t rounds = 1'000'000;
    SPSCRing<1024> ring;
    std::atomic<int> error{0};
    std::thread producer([&] {
        for (std::size_t i = 0; i < rounds; ++i)
            while (!ring.enqueue(i)) std::this_thread::yield();
    });
    std::thread consumer([&] {
        for (std::size_t i = 0; i < rounds; ++i) {
            std::uint64_t value;
            while (!ring.dequeue(value)) std::this_thread::yield();
            if (value != i) error.store(1, std::memory_order_relaxed);
        }
    });
    producer.join(); consumer.join();
    return error.load(std::memory_order_relaxed);
}
#endif
