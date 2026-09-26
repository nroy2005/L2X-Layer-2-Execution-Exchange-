#pragma once

#include "Order.hpp"

#include <cstddef>
#include <stdexcept>
#include <vector>

namespace core {

class MemoryPool {
 public:
  explicit MemoryPool(std::size_t capacity) : storage_(capacity) {
    free_list_.reserve(capacity);
    for (std::size_t i = 0; i < capacity; ++i) {
      free_list_.push_back(&storage_[i]);
    }
  }

  MemoryPool(const MemoryPool&) = delete;
  MemoryPool& operator=(const MemoryPool&) = delete;

  Order* allocate() {
    if (free_list_.empty()) {
      throw std::bad_alloc();
    }
    Order* o = free_list_.back();
    free_list_.pop_back();
    *o = Order{};
    return o;
  }

  void deallocate(Order* order) {
    if (order == nullptr) {
      return;
    }
    order->prev = nullptr;
    order->next = nullptr;
    free_list_.push_back(order);
  }

  [[nodiscard]] std::size_t available() const { return free_list_.size(); }
  [[nodiscard]] std::size_t capacity() const { return storage_.size(); }

 private:
  std::vector<Order> storage_;
  std::vector<Order*> free_list_;
};

}  // namespace core
