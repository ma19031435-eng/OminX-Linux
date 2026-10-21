cmake_minimum_required(VERSION 3.22)
project(OminXDesktopShell LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(Qt6 6.8 REQUIRED COMPONENTS Quick QuickControls2 QuickLayouts)
qt_standard_project_setup()
qt_add_executable(ominx-desktop main.cpp)
target_link_libraries(ominx-desktop PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::QuickLayouts)
# The login screen reuses the original OminX theme artwork unchanged.
configure_file(../sddm/ominx/Main.qml ${CMAKE_CURRENT_BINARY_DIR}/Greeter.qml COPYONLY)
set_source_files_properties(${CMAKE_CURRENT_BINARY_DIR}/Greeter.qml PROPERTIES QT_RESOURCE_ALIAS Greeter.qml)
qt_add_qml_module(ominx-desktop URI OminX.Shell VERSION 1.0
    RESOURCE_PREFIX /qt/qml NO_CACHEGEN
    QML_FILES Session.qml GreeterRoot.qml ${CMAKE_CURRENT_BINARY_DIR}/Greeter.qml)
set(FONT "${CMAKE_CURRENT_SOURCE_DIR}/../../build/sources/qtbase/src/3rdparty/wasm/DejaVuSans.ttf")
set_source_files_properties(${FONT} PROPERTIES QT_RESOURCE_ALIAS DejaVuSans.ttf)
qt_add_resources(ominx-desktop "font" PREFIX /fonts FILES ${FONT})
qt_import_plugins(ominx-desktop INCLUDE Qt6::QLinuxFbIntegrationPlugin)
qt_import_qml_plugins(ominx-desktop)
