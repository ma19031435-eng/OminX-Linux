pragma Singleton
import QtQuick

// Forge Studio uses the OminX brand palette, the same one as the desktop and Game Library.
QtObject {
    readonly property color navy: "#101d32"
    readonly property color chrome: "#0c1728"
    readonly property color panel: "#15294a"
    readonly property color gutter: "#0f2038"
    readonly property color line: "#24466a"
    readonly property color selection: "#123d46"
    readonly property color hover: "#1b3558"
    readonly property color accent: "#74e0c7"
    readonly property color accentDeep: "#4fbfa8"
    readonly property color slate: "#244767"
    readonly property color text: "#eff9f7"
    readonly property color muted: "#9fb6c6"
    readonly property color error: "#e87171"
    readonly property color warning: "#e8be60"
    readonly property color success: "#74e0c7"

    readonly property string uiFont: "Noto Sans"
    readonly property string codeFont: "DejaVu Sans Mono"
    readonly property int radius: 6
    readonly property int spacing: 8
    readonly property int codeSize: 14
}
