#pragma once

#include "MemoryPool.hpp"
#include "Order.hpp"
#include "RingBuffer.hpp"

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

namespace core {

struct PriceLevel {
  Order* head{nullptr};
  Order* tail{nullptr};
  uint32_t total_qty{0};
};

using TradeRing = SpscRingBuffer<TradeExecution, 65536>;

class OrderBook {
 public:
  explicit OrderBook(MemoryPool& pool, TradeRing& trades, const char* symbol = "BTC-USD");

  OrderBook(const OrderBook&) = delete;
  OrderBook& operator=(const OrderBook&) = delete;

  void add_limit_order(Order* order);
  uint32_t process_market_order(Side side, uint32_t quantity, uint32_t client_id = 0);
  bool cancel_order(uint64_t order_id);

  [[nodiscard]] std::size_t resting_orders() const { return order_index_.size(); }
  [[nodiscard]] uint64_t next_trade_id() const { return trade_seq_; }

 private:
  using BidBook = std::map<uint64_t, PriceLevel, std::greater<uint64_t>>;
  using AskBook = std::map<uint64_t, PriceLevel, std::less<uint64_t>>;

  void rest_order(Order* order);
  void link_back(PriceLevel& level, Order* order);
  void unlink_order(Order* order, uint64_t price, Side side);
  Order* best_opposite(Side incoming) const;
  uint32_t match_incoming(Order* taker, uint32_t max_qty);
  void emit_trade(const Order* maker, const Order* taker, uint32_t qty, uint64_t price);
  PriceLevel& level_for(Side side, uint64_t price);
  void prune_empty_level(Side side, uint64_t price);

  MemoryPool& pool_;
  TradeRing& trades_;
  char symbol_[16]{};
  BidBook bids_;
  AskBook asks_;
  std::unordered_map<uint64_t, Order*> order_index_;
  std::unordered_map<uint64_t, uint64_t> order_price_;
  std::unordered_map<uint64_t, Side> order_side_;
  uint64_t trade_seq_{1};
  uint64_t synthetic_market_id_{1};
};

}  // namespace core
