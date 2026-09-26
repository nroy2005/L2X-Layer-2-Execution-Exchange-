#include "MemoryPool.hpp"
#include "OrderBook.hpp"
#include "TradePublisher.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <random>
#include <string>
#include <vector>

using namespace core;

namespace {

struct LatencyStats {
  std::vector<uint64_t> samples_ns;
  void add(uint64_t ns) { samples_ns.push_back(ns); }
  uint64_t percentile(double p) const {
    if (samples_ns.empty()) {
      return 0;
    }
    std::vector<uint64_t> sorted = samples_ns;
    std::sort(sorted.begin(), sorted.end());
    const double rank = p * static_cast<double>(sorted.size() - 1);
    const std::size_t lo = static_cast<std::size_t>(rank);
    const std::size_t hi = std::min(lo + 1, sorted.size() - 1);
    const double frac = rank - static_cast<double>(lo);
    return static_cast<uint64_t>(sorted[lo] * (1.0 - frac) + sorted[hi] * frac);
  }
};

Order* make_limit(MemoryPool& pool, uint64_t id, Side side, uint64_t price, uint32_t qty) {
  Order* o = pool.allocate();
  o->order_id = id;
  o->client_id = 1;
  o->set_symbol("BTC-USD");
  o->side = side;
  o->price = price;
  o->quantity = qty;
  o->original_qty = qty;
  return o;
}

}  // namespace

int main(int argc, char** argv) {
  constexpr std::size_t kPoolCap = 200000;
  constexpr int kOrders = 100000;

  MemoryPool pool(kPoolCap);
  auto trade_ring_ptr = std::make_unique<TradeRing>();  // ~4.7MB: too big for the 1MB Windows stack
  TradeRing& trade_ring = *trade_ring_ptr;
  OrderBook book(pool, trade_ring, "BTC-USD");

  std::string log_path;
  if (argc > 1) {
    log_path = argv[1];
  }
  TradePublisher publisher(trade_ring, log_path);
  publisher.start();

  std::mt19937 rng(42);
  std::uniform_int_distribution<int> side_dist(0, 1);
  std::uniform_int_distribution<int> action_dist(0, 99);
  std::uniform_int_distribution<uint64_t> price_dist(990000, 1010000);
  std::uniform_int_distribution<uint32_t> qty_dist(1, 50);

  LatencyStats stats;
  stats.samples_ns.reserve(static_cast<std::size_t>(kOrders));

  const auto bench_start = std::chrono::steady_clock::now();

  std::vector<uint64_t> resting_ids;
  resting_ids.reserve(10000);

  for (int i = 0; i < kOrders; ++i) {
    const int roll = action_dist(rng);
    const auto t0 = std::chrono::steady_clock::now();

    if (roll < 70) {
      const Side side = side_dist(rng) == 0 ? Side::Buy : Side::Sell;
      const uint64_t order_id = static_cast<uint64_t>(i + 1);
      Order* o = make_limit(pool, order_id, side, price_dist(rng), qty_dist(rng));
      book.add_limit_order(o);
      if (roll < 35) {
        resting_ids.push_back(order_id);
      }
    } else if (roll < 85) {
      const Side side = side_dist(rng) == 0 ? Side::Buy : Side::Sell;
      book.process_market_order(side, qty_dist(rng));
    } else if (!resting_ids.empty()) {
      const uint64_t id = resting_ids.back();
      resting_ids.pop_back();
      book.cancel_order(id);
    } else {
      Order* o = make_limit(pool, static_cast<uint64_t>(i + 1), Side::Buy, price_dist(rng), qty_dist(rng));
      book.add_limit_order(o);
    }

    const auto t1 = std::chrono::steady_clock::now();
    stats.add(static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count()));
  }

  const auto bench_end = std::chrono::steady_clock::now();
  const double elapsed_s =
      std::chrono::duration_cast<std::chrono::duration<double>>(bench_end - bench_start).count();

  publisher.stop();

  const double ops_per_sec = static_cast<double>(kOrders) / elapsed_s;
  std::cout << "\n=== core_engine benchmark ===\n"
            << "orders_processed: " << kOrders << '\n'
            << "elapsed_sec: " << elapsed_s << '\n'
            << "throughput_ops_per_sec: " << ops_per_sec << '\n'
            << "latency_p50_ns: " << stats.percentile(0.50) << '\n'
            << "latency_p90_ns: " << stats.percentile(0.90) << '\n'
            << "latency_p99_ns: " << stats.percentile(0.99) << '\n'
            << "resting_orders: " << book.resting_orders() << '\n'
            << "trades_emitted: " << (book.next_trade_id() - 1) << '\n'
            << "trades_published: " << publisher.published_count() << '\n';

  return 0;
}
