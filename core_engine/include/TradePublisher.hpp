#pragma once

#include "RingBuffer.hpp"

#include <atomic>
#include <fstream>
#include <string>
#include <thread>

namespace core {

class TradePublisher {
 public:
  using TradeRing = SpscRingBuffer<TradeExecution, 65536>;

  TradePublisher(TradeRing& ring, std::string log_path = "");
  ~TradePublisher();

  TradePublisher(const TradePublisher&) = delete;
  TradePublisher& operator=(const TradePublisher&) = delete;

  void start();
  void stop();

  [[nodiscard]] uint64_t published_count() const {
    return published_.load(std::memory_order_relaxed);
  }

 private:
  void run();

  TradeRing& ring_;
  std::string log_path_;
  std::atomic<bool> running_{false};
  std::atomic<uint64_t> published_{0};
  std::thread worker_;
  std::ofstream log_file_;
};

}  // namespace core
