import QtQuick
import QtQuick.Layouts
import QtQuick.Window

// OminX window chrome. OminX apps are frameless, so each one draws its own
// minimize, maximize and close controls. Drag the bar to move the window;
// double-click it to maximize or restore.
Rectangle {
    id: bar
    required property var appWindow
    property string title: ""
    property string mark: "O"

    height: 40
    color: Theme.chrome

    // Drag and double-click. Sits under the buttons, so they receive their own clicks.
    MouseArea {
        anchors.fill: parent
        onPressed: bar.appWindow.startSystemMove()
        onDoubleClicked: bar.appWindow.visibility === Window.Maximized
                         ? bar.appWindow.showNormal() : bar.appWindow.showMaximized()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        spacing: 10

        // OminX logo, from desktop/branding/. Falls back to the letter if the file is missing.
        Image {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            Layout.alignment: Qt.AlignVCenter
            source: Qt.resolvedUrl("../../branding/ominx-logo-64.png")
            sourceSize.width: 64
            sourceSize.height: 64
            fillMode: Image.PreserveAspectFit
            smooth: true
            Text {
                anchors.centerIn: parent
                visible: parent.status !== Image.Ready
                text: bar.mark
                color: Theme.teal
                font.pixelSize: 12
                font.weight: Font.Black
            }
        }

        Text {
            Layout.fillWidth: true
            text: bar.title
            color: Theme.muted
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        ChromeButton {
            kind: "min"
            onActivated: bar.appWindow.showMinimized()
        }
        ChromeButton {
            kind: "max"
            onActivated: bar.appWindow.visibility === Window.Maximized
                         ? bar.appWindow.showNormal() : bar.appWindow.showMaximized()
        }
        ChromeButton {
            kind: "close"
            onActivated: bar.appWindow.close()
        }
    }

    // Drawn with shapes, not glyphs, so they look the same on every font.
    component ChromeButton: Rectangle {
        id: cb
        property string kind: "min"
        signal activated()

        Layout.preferredWidth: 46
        Layout.fillHeight: true
        color: hit.containsMouse ? (kind === "close" ? Theme.closeRed : Theme.hover) : "transparent"

        // Minimize: a short bar.
        Rectangle {
            visible: cb.kind === "min"
            anchors.centerIn: parent
            width: 10; height: 1
            color: Theme.text
        }
        // Maximize: a square outline.
        Rectangle {
            visible: cb.kind === "max"
            anchors.centerIn: parent
            width: 9; height: 9
            color: "transparent"
            border.width: 1
            border.color: Theme.text
        }
        // Close: two crossed bars.
        Rectangle {
            visible: cb.kind === "close"
            anchors.centerIn: parent
            width: 12; height: 1
            color: Theme.text
            rotation: 45
        }
        Rectangle {
            visible: cb.kind === "close"
            anchors.centerIn: parent
            width: 12; height: 1
            color: Theme.text
            rotation: -45
        }

        MouseArea {
            id: hit
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: cb.activated()
        }
    }
}
