#include "MemoryPool.hpp"

#include <cassert>
#include <iostream>

using namespace core;

int run_memory_pool_tests() {
  MemoryPool pool(4);
  assert(pool.capacity() == 4);
  assert(pool.available() == 4);

  Order* a = pool.allocate();
  Order* b = pool.allocate();
  assert(pool.available() == 2);
  a->order_id = 10;
  b->order_id = 20;

  pool.deallocate(a);
  assert(pool.available() == 3);

  Order* c = pool.allocate();
  assert(c->order_id == 0);
  c->order_id = 30;

  pool.deallocate(b);
  pool.deallocate(c);
  assert(pool.available() == 4);

  std::cout << "memory_pool tests ok\n";
  return 0;
}
