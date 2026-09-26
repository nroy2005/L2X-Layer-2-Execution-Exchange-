#include "TradePublisher.hpp"

#include <iostream>
#include <sstream>
#include <thread>

namespace core {

namespace {
const char* side_to_string(Side s) { return s == Side::Buy ? "buy" : "sell"; }

std::string to_json_line(const TradeExecution& t) {
  std::ostringstream os;
  os << '{'
     << "\"type\":\"trade\""
     << ",\"timestamp_ns\":" << t.timestamp_ns
     << ",\"trade_id\":" << t.trade_id
     << ",\"symbol\":\"" << t.symbol << '"'
     << ",\"price\":" << t.price
     << ",\"quantity\":" << t.quantity
     << ",\"side\":\"" << side_to_string(t.aggressive_side) << '"'
     << ",\"maker_order_id\":" << t.maker_order_id
     << ",\"taker_order_id\":" << t.taker_order_id
     << '}';
  return os.str();
}
}  // namespace

TradePublisher::TradePublisher(TradeRing& ring, std::string log_path)
    : ring_(ring), log_path_(std::move(log_path)) {}

TradePublisher::~TradePublisher() { stop(); }

void TradePublisher::start() {
  if (running_.exchange(true)) {
    return;
  }
  if (!log_path_.empty()) {
    log_file_.open(log_path_, std::ios::out | std::ios::app);
  }
  worker_ = std::thread([this] { run(); });
}

void TradePublisher::stop() {
  if (!running_.exchange(false)) {
    return;
  }
  if (worker_.joinable()) {
    worker_.join();
  }
  if (log_file_.is_open()) {
    log_file_.close();
  }
}

void TradePublisher::run() {
  TradeExecution ev{};
  while (running_.load(std::memory_order_relaxed)) {
    if (ring_.try_pop(ev)) {
      const std::string line = to_json_line(ev);
      std::cout << line << '\n';
      if (log_file_.is_open()) {
        log_file_ << line << '\n';
      }
      published_.fetch_add(1, std::memory_order_relaxed);
    } else {
      std::this_thread::yield();
    }
  }
  while (ring_.try_pop(ev)) {
    const std::string line = to_json_line(ev);
    std::cout << line << '\n';
    if (log_file_.is_open()) {
      log_file_ << line << '\n';
    }
    published_.fetch_add(1, std::memory_order_relaxed);
  }
}

}  // namespace core
