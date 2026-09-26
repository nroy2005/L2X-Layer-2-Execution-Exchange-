#include "MemoryPool.hpp"
#include "OrderBook.hpp"

#include <cassert>
#include <iostream>

using namespace core;

namespace {

Order* limit(MemoryPool& pool, uint64_t id, Side side, uint64_t px, uint32_t qty) {
  Order* o = pool.allocate();
  o->order_id = id;
  o->set_symbol("BTC-USD");
  o->side = side;
  o->price = px;
  o->quantity = qty;
  o->original_qty = qty;
  return o;
}

}  // namespace

int run_order_book_tests() {
  MemoryPool pool(1024);
  OrderBook::TradeRing ring;
  OrderBook book(pool, ring, "BTC-USD");

  Order* ask1 = limit(pool, 1, Side::Sell, 10000, 10);
  book.add_limit_order(ask1);
  assert(book.resting_orders() == 1);

  Order* bid_hit = limit(pool, 2, Side::Buy, 10000, 4);
  book.add_limit_order(bid_hit);
  assert(book.resting_orders() == 1);
  assert(book.next_trade_id() == 2);

  Order* bid2 = limit(pool, 3, Side::Buy, 9900, 5);
  book.add_limit_order(bid2);
  assert(book.resting_orders() == 2);

  const uint32_t filled = book.process_market_order(Side::Sell, 3);
  assert(filled == 3);
  assert(book.next_trade_id() >= 3);

  Order* partial = limit(pool, 4, Side::Sell, 9800, 10);
  book.add_limit_order(partial);
  assert(book.resting_orders() >= 2);

  Order* mkt_buy = limit(pool, 999, Side::Buy, 0, 0);
  (void)mkt_buy;
  const uint32_t mkt_fill = book.process_market_order(Side::Buy, 7);
  assert(mkt_fill > 0);

  assert(book.cancel_order(3));
  assert(!book.cancel_order(999999));

  Order* self = limit(pool, 5, Side::Buy, 9700, 2);
  book.add_limit_order(self);
  assert(book.resting_orders() >= 1);
  assert(book.cancel_order(5));

  Order* zero = limit(pool, 6, Side::Buy, 9600, 0);
  book.add_limit_order(zero);
  pool.deallocate(zero);

  std::cout << "order_book tests ok\n";
  return 0;
}
