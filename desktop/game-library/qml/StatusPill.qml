import QtQuick

// A small rounded label used for publisher and scheduling state.
Rectangle {
    id: pill
    property string label: ""
    property color tint: Theme.muted

    implicitHeight: 26
    implicitWidth: caption.implicitWidth + 22
    radius: 13
    color: Qt.rgba(tint.r, tint.g, tint.b, 0.14)
    border.width: 1
    border.color: Qt.rgba(tint.r, tint.g, tint.b, 0.5)

    Text {
        id: caption
        anchors.centerIn: parent
        text: pill.label
        color: pill.tint
        font.pixelSize: 12
        font.weight: Font.DemiBold
    }
}
