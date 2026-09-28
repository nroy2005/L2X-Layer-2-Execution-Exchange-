#include <iostream>

extern int run_memory_pool_tests();
extern int run_ring_buffer_tests();
extern int run_order_book_tests();

int main() {
  const int a = run_memory_pool_tests();
  const int b = run_ring_buffer_tests();
  const int c = run_order_book_tests();
  if (a == 0 && b == 0 && c == 0) {
    std::cout << "All tests passed.\n";
    return 0;
  }
  std::cerr << "Tests failed.\n";
  return 1;
}
