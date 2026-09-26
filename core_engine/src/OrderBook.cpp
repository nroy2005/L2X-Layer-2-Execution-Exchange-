#include "OrderBook.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>

namespace core {

namespace {
uint64_t now_ns() {
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
}
}  // namespace

OrderBook::OrderBook(MemoryPool& pool, TradeRing& trades, const char* symbol)
    : pool_(pool), trades_(trades) {
  if (symbol != nullptr) {
    std::strncpy(symbol_, symbol, sizeof(symbol_) - 1);
  }
  symbol_[sizeof(symbol_) - 1] = '\0';
}

void OrderBook::link_back(PriceLevel& level, Order* order) {
  order->prev = level.tail;
  order->next = nullptr;
  if (level.tail != nullptr) {
    level.tail->next = order;
  } else {
    level.head = order;
  }
  level.tail = order;
  level.total_qty += order->quantity;
}

void OrderBook::unlink_order(Order* order, uint64_t price, Side side) {
  PriceLevel& level = level_for(side, price);
  if (order->prev != nullptr) {
    order->prev->next = order->next;
  } else {
    level.head = order->next;
  }
  if (order->next != nullptr) {
    order->next->prev = order->prev;
  } else {
    level.tail = order->prev;
  }
  level.total_qty -= order->quantity;
  order->prev = nullptr;
  order->next = nullptr;
  prune_empty_level(side, price);
}

PriceLevel& OrderBook::level_for(Side side, uint64_t price) {
  if (side == Side::Buy) {
    return bids_[price];
  }
  return asks_[price];
}

void OrderBook::prune_empty_level(Side side, uint64_t price) {
  if (side == Side::Buy) {
    auto it = bids_.find(price);
    if (it != bids_.end() && it->second.head == nullptr) {
      bids_.erase(it);
    }
  } else {
    auto it = asks_.find(price);
    if (it != asks_.end() && it->second.head == nullptr) {
      asks_.erase(it);
    }
  }
}

void OrderBook::rest_order(Order* order) {
  PriceLevel& level = level_for(order->side, order->price);
  link_back(level, order);
  order_index_[order->order_id] = order;
  order_price_[order->order_id] = order->price;
  order_side_[order->order_id] = order->side;
}

Order* OrderBook::best_opposite(Side incoming) const {
  if (incoming == Side::Buy) {
    if (asks_.empty()) {
      return nullptr;
    }
    const PriceLevel& lvl = asks_.begin()->second;
    return lvl.head;
  }
  if (bids_.empty()) {
    return nullptr;
  }
  const PriceLevel& lvl = bids_.begin()->second;
  return lvl.head;
}

void OrderBook::emit_trade(const Order* maker, const Order* taker, uint32_t qty, uint64_t price) {
  TradeExecution ev{};
  ev.timestamp_ns = now_ns();
  ev.trade_id = trade_seq_++;
  std::strncpy(ev.symbol, maker->symbol, sizeof(ev.symbol) - 1);
  ev.price = price;
  ev.quantity = qty;
  ev.aggressive_side = taker->side;
  ev.maker_order_id = maker->order_id;
  ev.taker_order_id = taker->order_id;
  while (!trades_.try_push(ev)) {
    // Producer spin: matching path stays non-blocking except brief retry on full buffer.
  }
}

uint32_t OrderBook::match_incoming(Order* taker, uint32_t max_qty) {
  uint32_t remaining = max_qty;
  while (remaining > 0) {
    Order* maker = best_opposite(taker->side);
    if (maker == nullptr) {
      break;
    }
    if (taker->side == Side::Buy && taker->price < maker->price) {
      break;
    }
    if (taker->side == Side::Sell && taker->price > maker->price) {
      break;
    }

    const uint32_t fill_qty = std::min(remaining, maker->quantity);
    const uint64_t trade_price = maker->price;
    emit_trade(maker, taker, fill_qty, trade_price);

    maker->quantity -= fill_qty;
    remaining -= fill_qty;
    taker->quantity -= fill_qty;

    const uint64_t maker_price = order_price_.at(maker->order_id);
    const Side maker_side = order_side_.at(maker->order_id);
    PriceLevel& lvl = level_for(maker_side, maker_price);
    lvl.total_qty -= fill_qty;

    if (maker->quantity == 0) {
      unlink_order(maker, maker_price, maker_side);
      order_index_.erase(maker->order_id);
      order_price_.erase(maker->order_id);
      order_side_.erase(maker->order_id);
      pool_.deallocate(maker);
    }
  }
  return max_qty - remaining;
}

void OrderBook::add_limit_order(Order* order) {
  if (order == nullptr || order->quantity == 0) {
    return;
  }
  order->original_qty = order->quantity;
  if (order->symbol[0] == '\0') {
    std::strncpy(order->symbol, symbol_, sizeof(order->symbol) - 1);
  }

  match_incoming(order, order->quantity);

  if (order->quantity > 0) {
    rest_order(order);
  } else {
    pool_.deallocate(order);
  }
}

uint32_t OrderBook::process_market_order(Side side, uint32_t quantity, uint32_t client_id) {
  if (quantity == 0) {
    return 0;
  }
  Order* taker = pool_.allocate();
  taker->order_id = synthetic_market_id_++ | (1ULL << 63);
  taker->client_id = client_id;
  std::strncpy(taker->symbol, symbol_, sizeof(taker->symbol) - 1);
  taker->side = side;
  taker->price = (side == Side::Buy) ? UINT64_MAX : 0;
  taker->quantity = quantity;
  taker->original_qty = quantity;

  const uint32_t filled = match_incoming(taker, quantity);
  pool_.deallocate(taker);
  return filled;
}

bool OrderBook::cancel_order(uint64_t order_id) {
  auto it = order_index_.find(order_id);
  if (it == order_index_.end()) {
    return false;
  }
  Order* order = it->second;
  const uint64_t price = order_price_.at(order_id);
  const Side side = order_side_.at(order_id);
  unlink_order(order, price, side);
  order_index_.erase(it);
  order_price_.erase(order_id);
  order_side_.erase(order_id);
  pool_.deallocate(order);
  return true;
}

}  // namespace core
