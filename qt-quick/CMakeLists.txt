cmake_minimum_required(VERSION 3.16)
project(bench_qtquick LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Quick QuickControls2)

foreach(app hello list forms textview)
    add_executable(bench_qtquick_${app} ${app}.cpp ${app}.qrc)
    target_link_libraries(bench_qtquick_${app} PRIVATE Qt6::Quick Qt6::QuickControls2)
endforeach()
