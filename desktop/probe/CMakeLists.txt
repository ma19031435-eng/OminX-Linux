cmake_minimum_required(VERSION 3.22)
project(OminXGraphicsProbe LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets)
qt_add_executable(ominx-graphics-probe main.cpp)
target_link_libraries(ominx-graphics-probe PRIVATE Qt6::Widgets)
qt_import_plugins(ominx-graphics-probe INCLUDE
    Qt6::QLinuxFbIntegrationPlugin Qt6::QOffscreenIntegrationPlugin)
