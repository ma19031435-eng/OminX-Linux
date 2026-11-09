cmake_minimum_required(VERSION 3.22)
project(forge-studio VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2)
qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(forge-studio host/forge_studio.cpp host/forge_bridge.cpp)

qt_add_qml_module(forge-studio
    URI ForgeStudio
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/Navigator.qml
        qml/Editor.qml
        qml/OutputPanel.qml
        qml/NewProjectDialog.qml
        qml/Theme.qml
    SOURCES host/forge_bridge.h
)

target_link_libraries(forge-studio PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
    Qt6::QuickControls2
)

install(TARGETS forge-studio RUNTIME DESTINATION bin)
