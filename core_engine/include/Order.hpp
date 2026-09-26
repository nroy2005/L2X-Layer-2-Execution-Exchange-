#pragma once

#include <cstdint>
#include <cstring>

namespace core {

enum class Side : uint8_t { Buy = 0, Sell = 1 };

inline Side opposite(Side s) {
  return s == Side::Buy ? Side::Sell : Side::Buy;
}

struct Order {
  uint64_t order_id{0};
  uint32_t client_id{0};
  char symbol[16]{};
  Side side{Side::Buy};
  uint64_t price{0};     // fixed-point: price in ticks/cents
  uint32_t quantity{0};
  uint32_t original_qty{0};

  Order* prev{nullptr};
  Order* next{nullptr};

  void set_symbol(const char* sym) {
    if (sym == nullptr) {
      symbol[0] = '\0';
      return;
    }
    std::strncpy(symbol, sym, sizeof(symbol) - 1);
    symbol[sizeof(symbol) - 1] = '\0';
  }
};

struct TradeExecution {
  uint64_t timestamp_ns{0};
  uint64_t trade_id{0};
  char symbol[16]{};
  uint64_t price{0};
  uint32_t quantity{0};
  Side aggressive_side{Side::Buy};
  uint64_t maker_order_id{0};
  uint64_t taker_order_id{0};
};

}  // namespace core
