#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace core {

template <typename T, std::size_t Capacity>
class SpscRingBuffer {
  static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be a power of two");
  static_assert(std::is_trivially_copyable_v<T>, "T must be trivially copyable for SPSC ring");

 public:
  SpscRingBuffer() : head_(0), tail_(0) {}

  SpscRingBuffer(const SpscRingBuffer&) = delete;
  SpscRingBuffer& operator=(const SpscRingBuffer&) = delete;

  bool try_push(const T& item) {
    const std::size_t head = head_.load(std::memory_order_relaxed);
    const std::size_t next = (head + 1) & kMask;
    if (next == tail_.load(std::memory_order_acquire)) {
      return false;
    }
    slots_[head] = item;
    head_.store(next, std::memory_order_release);
    return true;
  }

  bool try_pop(T& out) {
    const std::size_t tail = tail_.load(std::memory_order_relaxed);
    if (tail == head_.load(std::memory_order_acquire)) {
      return false;
    }
    out = slots_[tail];
    tail_.store((tail + 1) & kMask, std::memory_order_release);
    return true;
  }

  [[nodiscard]] bool empty() const {
    return tail_.load(std::memory_order_acquire) == head_.load(std::memory_order_acquire);
  }

 private:
  static constexpr std::size_t kMask = Capacity - 1;
  alignas(64) std::atomic<std::size_t> head_{0};
  alignas(64) std::atomic<std::size_t> tail_{0};
  T slots_[Capacity]{};
};

}  // namespace core
