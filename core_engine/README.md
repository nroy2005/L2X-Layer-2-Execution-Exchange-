# core_engine — C++20 Limit Order Book

High-throughput matching core with price-time priority, pool-backed orders, and decoupled trade publishing via an SPSC ring buffer.

## Layout

```
core_engine/
  include/   Order.hpp, OrderBook.hpp, MemoryPool.hpp, RingBuffer.hpp, TradePublisher.hpp
  src/       OrderBook.cpp, TradePublisher.cpp
  tests/     Unit tests (limit/market/partial fill/cancel)
  main.cpp   100k-order latency/throughput benchmark
```

## Build

```bash
cd core_engine
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

Windows (MSVC or MinGW) uses the same commands if CMake and a C++20 compiler are on `PATH`.

## Run tests

```bash
./build/core_engine_tests
ctest --test-dir build
```

## Benchmark

Optional second argument writes JSON trade lines to a log file; stdout always receives serialized executions from the publisher thread.

```bash
./build/core_engine_bench trades.jsonl
```

The driver submits 100,000 synthetic limit/market/cancel operations and reports p50/p90/p99 match latency (nanoseconds) and throughput (ops/sec).

## Matching semantics

- **Limit orders**: Match against the opposite side while price crosses; remainder rests FIFO at its price level.
- **Market orders**: Walk best opposite prices until quantity fills or liquidity runs out.
- **Cancel**: `O(1)` lookup by `order_id`, unlink from intrusive doubly-linked queue, return slot to `MemoryPool`.
- **Trades**: Pushed to a lock-free SPSC ring; a worker thread emits JSON compatible with downstream surveillance ingestion (`type`, `symbol`, `price`, `quantity`, `side`, timestamps).

## Order fields

Fixed-size `Order` uses integer `price` (fixed-point ticks/cents), intrusive `prev`/`next` pointers per price level, and no heap allocation on the hot path when the pool has capacity.
