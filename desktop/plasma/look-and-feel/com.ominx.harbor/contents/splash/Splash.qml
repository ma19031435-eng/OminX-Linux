import QtQuick

// OminX Harbor splash: the logo, centred on the brand navy, shown while the
// session starts. Plasma sets `stage` as startup progresses; the logo does not
// change with it, so the splash stays calm.
Rectangle {
    id: root
    property int stage: 0
    color: "#101d32"

    Image {
        id: mark
        anchors.centerIn: parent
        width: Math.min(root.width, root.height) * 0.28
        height: width
        source: Qt.resolvedUrl("../images/ominx-logo.svg")
        sourceSize.width: width * 2
        sourceSize.height: height * 2
        fillMode: Image.PreserveAspectFit
        smooth: true
    }
}
