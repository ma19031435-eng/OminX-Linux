import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The selected title in full. Every field comes from the backend's schema-1 JSON.
Rectangle {
    id: panel
    property var game: null
    signal closeRequested()
    signal launchRequested(string id)

    color: Theme.sidebar
    border.width: 0

    Rectangle { width: 1; height: parent.height; color: Theme.line; anchors.left: parent.left }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 26
        spacing: 14
        visible: panel.game !== null

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: panel.game ? panel.game.name : ""
                color: Theme.text
                font.pixelSize: 22
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            ToolButton {
                text: "×"
                onClicked: panel.closeRequested()
                contentItem: Text {
                    text: parent.text
                    color: Theme.muted
                    font.pixelSize: 22
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle { color: "transparent" }
            }
        }

        StatusPill {
            label: panel.game ? Theme.publisherLabel(panel.game.publisher_status) : ""
            tint: panel.game ? Theme.publisherColor(panel.game.publisher_status) : Theme.muted
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.line
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 16
            rowSpacing: 12

            Repeater {
                model: panel.game ? [
                    ["Runner", panel.game.runner === "proton" ? "Proton" : "Wine"],
                    ["Anti-cheat", panel.game.anticheat === "none" ? "None" : panel.game.anticheat.toUpperCase()],
                    ["Requires", panel.game.requires === "none" ? "Nothing extra" : "EAC Linux v2"],
                    ["Install folder", panel.game.install_dir],
                    ["Program", panel.game.program]
                ] : []
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.columnSpan: modelData[0] === "Program" || modelData[0] === "Install folder" ? 2 : 1
                    Layout.fillWidth: true
                    spacing: 3
                    Text { text: modelData[0].toUpperCase(); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1 }
                    Text {
                        Layout.fillWidth: true
                        text: modelData[1]
                        color: Theme.text
                        font.pixelSize: 13
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: schedText.implicitHeight + 24
            radius: 12
            color: Theme.card
            border.width: 1
            border.color: Theme.line

            ColumnLayout {
                id: schedText
                anchors.fill: parent
                anchors.margins: 12
                spacing: 4
                Text {
                    text: "SCHEDULING"
                    color: Theme.muted
                    font.pixelSize: 10
                    font.letterSpacing: 1
                }
                Text {
                    Layout.fillWidth: true
                    text: panel.game ? Theme.schedLabel(panel.game.scheduling.state) : ""
                    color: panel.game ? Theme.schedColor(panel.game.scheduling.state) : Theme.muted
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    text: panel.game && panel.game.scheduling.detail ? panel.game.scheduling.detail : ""
                    color: Theme.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    visible: text.length > 0
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: panel.game && panel.game.notes ? panel.game.notes : ""
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            visible: text.length > 0
        }

        Item { Layout.fillHeight: true }

        Button {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            enabled: panel.game !== null && panel.game.launchable === true
            text: enabled ? "Launch " + panel.game.name : Theme.humanRefusal(panel.game ? panel.game.refusal : "")
            onClicked: panel.launchRequested(panel.game.id)
            contentItem: Text {
                text: parent.text
                color: parent.enabled ? "#06141a" : Theme.muted
                font.pixelSize: parent.enabled ? 14 : 12
                font.weight: parent.enabled ? Font.DemiBold : Font.Normal
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle {
                radius: 10
                color: parent.enabled ? Theme.accent : "transparent"
                border.width: parent.enabled ? 0 : 1
                border.color: Theme.disabled
            }
        }
    }
}
