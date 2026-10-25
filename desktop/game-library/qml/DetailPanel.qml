import QtQuick
import QtQuick.Layouts

// The selected title. It is the only place with a launch action, so the page
// has at most one button. `game` is always an object; Main passes a blank one
// when nothing is selected.
Rectangle {
    id: panel
    property var game: ({})
    property string iconBase: ""
    signal launchRequested()

    readonly property bool launchable: game.launchable === true
    readonly property bool hasIcon: game.icon !== undefined && game.icon !== "" && art.status === Image.Ready

    color: Theme.chrome

    // Left edge rule instead of a box border.
    Rectangle {
        anchors.left: parent.left
        width: 1
        height: parent.height
        color: Theme.line
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 26
        spacing: 16

        Item {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 120
            Layout.preferredHeight: 120
            opacity: panel.launchable ? 1.0 : 0.5

            Rectangle {
                anchors.fill: parent
                radius: 28
                color: Theme.tileColor(panel.game.runner)
                visible: !panel.hasIcon
                Text {
                    anchors.centerIn: parent
                    text: panel.game.name ? panel.game.name.charAt(0).toUpperCase() : ""
                    color: Theme.text
                    font.pixelSize: 52
                    font.weight: Font.Black
                }
            }

            Image {
                id: art
                anchors.fill: parent
                source: (panel.game.icon !== undefined && panel.game.icon !== "" && panel.iconBase !== "")
                        ? panel.iconBase + "/" + panel.game.icon : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: panel.hasIcon
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: panel.game.name || ""
                color: Theme.text
                font.pixelSize: 22
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: Theme.publisherLabel(panel.game.publisher_status || "")
                color: Theme.publisherColor(panel.game.publisher_status || "")
                font.pixelSize: 13
            }
        }

        // Facts, one per line. Plain labels, no grid of boxes.
        Repeater {
            model: panel.game.name ? [
                ["Runner", panel.game.runner === "proton" ? "Proton" : "Wine"],
                ["Anti-cheat", panel.game.anticheat === "none" ? "None" : (panel.game.anticheat || "").toUpperCase()],
                ["Requires", panel.game.requires === "none" ? "Nothing extra" : "EAC Linux v2"],
                ["Program", panel.game.program || ""]
            ] : []
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 12
                Text {
                    Layout.preferredWidth: 84
                    text: modelData[0]
                    color: Theme.muted
                    font.pixelSize: 12
                }
                Text {
                    Layout.fillWidth: true
                    text: modelData[1]
                    color: Theme.text
                    font.pixelSize: 13
                    elide: Text.ElideMiddle
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: text.length > 0
            text: panel.game.scheduling ? Theme.schedLabel(panel.game.scheduling.state) : ""
            color: panel.game.scheduling ? Theme.schedColor(panel.game.scheduling.state) : Theme.muted
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: text.length > 0
            text: panel.game.notes || ""
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }

        Item { Layout.fillHeight: true }

        // The one action. When blocked, the reason is text, not a disabled button.
        Rectangle {
            visible: panel.launchable
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            radius: 12
            color: launchMouse.containsMouse ? Theme.accent : Theme.accentDeep

            Text {
                anchors.centerIn: parent
                text: "Launch"
                color: Theme.navy
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
            MouseArea {
                id: launchMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: panel.launchRequested()
            }
        }

        Text {
            visible: !panel.launchable
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: Theme.humanRefusal(panel.game.refusal || "")
            color: Theme.muted
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }
    }
}
