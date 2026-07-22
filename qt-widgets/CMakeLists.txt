cmake_minimum_required(VERSION 3.16)
project(bench_qt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets)

foreach(app hello list forms textview)
    add_executable(bench_qt_${app} ${app}.cpp)
    target_link_libraries(bench_qt_${app} PRIVATE Qt6::Widgets)
endforeach()
