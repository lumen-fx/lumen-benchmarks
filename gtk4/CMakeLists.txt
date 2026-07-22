cmake_minimum_required(VERSION 3.16)
project(bench_gtk4 LANGUAGES C)

set(CMAKE_C_STANDARD 11)

find_package(PkgConfig REQUIRED)
pkg_check_modules(GTK4 REQUIRED IMPORTED_TARGET gtk4)

foreach(app hello list forms textview)
    add_executable(bench_gtk4_${app} ${app}.c)
    target_link_libraries(bench_gtk4_${app} PRIVATE PkgConfig::GTK4 m)
endforeach()
