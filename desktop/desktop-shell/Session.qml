// Original OminX desktop shell. Repository license applies.
// Every control performs a real action through the session context.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: desktop
    objectName: "ominxDesktop"
    width: 1440; height: 900
    color: "#12263c"
    readonly property color accent: "#4fa3ff"
    property date clock: new Date()
    readonly property bool compact: height < 760

    component MenuButton: Button {
        id: menuButton
        implicitHeight: 38
        contentItem: Text {
            text: menuButton.text; color: "#e7f2fa"; font.pixelSize: 14
            verticalAlignment: Text.AlignVCenter; leftPadding: 10
        }
        background: Rectangle {
            radius: 8
            color: menuButton.down ? "#24506f"
                                   : (menuButton.hovered || menuButton.activeFocus ? "#1b3d56" : "transparent")
        }
    }

    Timer { interval: 1000; repeat: true; running: true; onTriggered: desktop.clock = new Date() }

    gradient: Gradient {
        GradientStop { position: 0; color: "#1b3a5c" }
        GradientStop { position: 0.6; color: "#15293f" }
        GradientStop { position: 1; color: "#0e1c2c" }
    }
    Canvas {
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset()
            var w = width, h = height
            c.strokeStyle = "#274b6e"; c.lineWidth = 2
            for (var i = 0; i < 12; i++) {
                c.beginPath()
                c.moveTo(w * 0.62 + i * 26, 0)
                c.bezierCurveTo(w * 0.34 + i * 24, h * 0.4, w * 0.5 + i * 26, h, w, h * 0.72 + i * 12)
                c.stroke()
            }
        }
    }
    Row {
        anchors.top: parent.top; anchors.left: parent.left; anchors.margins: 24; spacing: 10
        Rectangle {
            width: 26; height: 26; radius: 7; color: "#f2c14e"
            Text { anchors.centerIn: parent; text: "X"; font.pixelSize: 17; font.bold: true; color: "#22303f" }
        }
        Text { text: "OminX"; color: "#f3f8fb"; font.pixelSize: 20; font.weight: Font.DemiBold }
    }

    // Real session facts, opened from the start menu.
    Popup {
        id: information
        objectName: "sessionInformation"
        anchors.centerIn: parent
        width: Math.min(520, desktop.width - 48); height: column.implicitHeight + 56
        modal: true; focus: true; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        background: Rectangle { radius: 16; color: "#f0101c2a"; border.color: "#33556f"; border.width: 1 }
        ColumnLayout {
            id: column
            anchors.centerIn: parent; width: parent.width - 48; spacing: 10
            Text { text: qsTr("This session"); color: "#eaf4fb"; font.pixelSize: 20; font.weight: Font.DemiBold }
            Repeater {
                model: session ? session.facts : []
                Text {
                    Layout.fillWidth: true
                    text: modelData; color: "#b9d3e6"; font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
            }
            Button {
                objectName: "informationClose"
                Layout.alignment: Qt.AlignRight
                text: qsTr("Close")
                onClicked: information.close()
            }
        }
    }

    Popup {
        id: startMenu
        objectName: "startMenu"
        x: 8; y: desktop.height - height - taskbar.height - 8
        width: 300; height: menuColumn.implicitHeight + 28
        modal: false; focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { radius: 14; color: "#f40d1a26"; border.color: "#31536c"; border.width: 1 }
        onOpened: logoutButton.forceActiveFocus()
        ColumnLayout {
            id: menuColumn
            anchors.fill: parent; anchors.margins: 14; spacing: 8
            RowLayout {
                spacing: 10
                Rectangle {
                    width: 38; height: 38; radius: 19; color: "#1d3c56"; border.color: "#4a7fa5"
                    Text {
                        anchors.centerIn: parent
                        text: session && session.userName.length ? session.userName.charAt(0).toUpperCase() : "O"
                        color: "#9fd0f5"; font.pixelSize: 17
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: session ? session.userName : ""
                    color: "#eaf4fb"; font.pixelSize: 16; elide: Text.ElideRight
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#2b4a63" }
            MenuButton {
                id: logoutButton; objectName: "logoutButton"
                Layout.fillWidth: true
                text: qsTr("Log out")
                onClicked: { startMenu.close(); session.logout() }
            }
            MenuButton {
                objectName: "restartButton"
                Layout.fillWidth: true
                text: qsTr("Restart")
                onClicked: { startMenu.close(); session.reboot() }
            }
            MenuButton {
                objectName: "powerOffButton"
                Layout.fillWidth: true
                text: qsTr("Shut down")
                onClicked: { startMenu.close(); session.powerOff() }
            }
            MenuButton {
                objectName: "informationButton"
                Layout.fillWidth: true
                text: qsTr("Session information")
                onClicked: { startMenu.close(); information.open() }
            }
        }
    }

    Rectangle {
        id: taskbar
        objectName: "taskbar"
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: desktop.compact ? 40 : 48
        color: "#0b1520"
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 12; spacing: 10
            Button {
                id: startButton; objectName: "startButton"
                Layout.preferredWidth: 46; Layout.fillHeight: true
                contentItem: Rectangle {
                    radius: 8; color: startButton.down ? "#2b5c80" : (startButton.hovered || startButton.activeFocus ? "#1d4566" : "transparent")
                    Text {
                        anchors.centerIn: parent; text: "X"
                        color: desktop.accent; font.pixelSize: 19; font.bold: true
                    }
                }
                background: Item {}
                onClicked: startMenu.opened ? startMenu.close() : startMenu.open()
            }
            Item { Layout.fillWidth: true }
            Column {
                Layout.alignment: Qt.AlignVCenter
                Text {
                    anchors.right: parent.right
                    text: Qt.formatTime(desktop.clock, "hh:mm"); color: "#f0f7fb"; font.pixelSize: 15
                }
                Text {
                    anchors.right: parent.right
                    text: Qt.formatDate(desktop.clock, "ddd d MMM"); color: "#a9c6da"; font.pixelSize: 11
                }
            }
        }
    }
    Shortcut {
        sequences: ["Meta", "Esc"]
        onActivated: startMenu.opened ? startMenu.close() : startMenu.open()
    }
    // Keyboard-only power action, matching the login screen.
    Shortcut {
        sequence: "Ctrl+Alt+End"
        onActivated: session.powerOff()
    }
    Component.onCompleted: startButton.forceActiveFocus()
}
