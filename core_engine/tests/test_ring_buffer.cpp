#include "RingBuffer.hpp"

#include <cassert>
#include <iostream>
#include <thread>

using namespace core;

int run_ring_buffer_tests() {
  SpscRingBuffer<int, 8> ring;
  assert(ring.empty());

  assert(ring.try_push(1));
  assert(ring.try_push(2));
  int v = 0;
  assert(ring.try_pop(v) && v == 1);
  assert(ring.try_pop(v) && v == 2);
  assert(ring.empty());

  for (int i = 0; i < 7; ++i) {
    assert(ring.try_push(i));
  }
  assert(!ring.try_push(99));

  for (int i = 0; i < 7; ++i) {
    assert(ring.try_pop(v) && v == i);
  }

  std::atomic<bool> done{false};
  std::thread producer([&] {
    for (int i = 0; i < 1000; ++i) {
      while (!ring.try_push(i)) {
      }
    }
    done.store(true);
  });

  int count = 0;
  int last = -1;
  while (count < 1000) {
    if (ring.try_pop(v)) {
      assert(v > last);
      last = v;
      ++count;
    }
  }
  producer.join();
  assert(done.load());

  std::cout << "ring_buffer tests ok\n";
  return 0;
}
