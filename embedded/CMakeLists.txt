cmake_minimum_required(VERSION 3.20)
project(EventVaultR CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra)

# Source directories directory
include_directories(include)

# Define the source files
set(SOURCES
    src/dwt.cpp
    src/dwt_fixed.cpp
    src/guardrail.cpp
    src/escrow.cpp
    src/uncertainty.cpp
    src/resource_controller.cpp
    src/telemetry.cpp
    src/pipeline.cpp
)

# Create a static library for the core modules
add_library(eventvault_core STATIC ${SOURCES})

# Create the main executable
add_executable(eventvault_app app/main.cpp)
target_link_libraries(eventvault_app PRIVATE eventvault_core)

add_executable(fixed_point_eval app/fixed_point_eval.cpp)
target_link_libraries(fixed_point_eval PRIVATE eventvault_core)

# Tests
add_executable(test_dwt tests/test_dwt.cpp)
target_link_libraries(test_dwt PRIVATE eventvault_core)
