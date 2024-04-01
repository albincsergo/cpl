cmake_minimum_required(VERSION 3.10)
project(cpl)

find_package(LLVM REQUIRED CONFIG)

include_directories(${LLVM_INCLUDE_DIRS})
include_directories(${CMAKE_SOURCE_DIR}/src)
add_definitions(${LLVM_DEFINITIONS})

add_executable(cpl src/CPL.cpp)

target_link_libraries(cpl LLVM)