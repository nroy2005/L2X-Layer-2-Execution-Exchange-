cmake_minimum_required(VERSION 3.20)
project(core_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(core_engine_lib
  src/OrderBook.cpp
  src/TradePublisher.cpp
)
target_include_directories(core_engine_lib PUBLIC include)

if(MSVC)
  target_compile_options(core_engine_lib PRIVATE /W4 /O2)
else()
  target_compile_options(core_engine_lib PRIVATE -Wall -Wextra -Wpedantic -O3)
endif()

add_executable(core_engine_bench main.cpp)
target_link_libraries(core_engine_bench PRIVATE core_engine_lib)

add_executable(core_engine_tests
  tests/test_main.cpp
  tests/test_memory_pool.cpp
  tests/test_ring_buffer.cpp
  tests/test_order_book.cpp
)
target_link_libraries(core_engine_tests PRIVATE core_engine_lib)
if(NOT MSVC)
  target_compile_options(core_engine_tests PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
add_test(NAME core_engine_tests COMMAND core_engine_tests)
