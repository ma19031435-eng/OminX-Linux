import QtQuick
import QtQuick.Layouts

// One title. `game` is one entry of the backend's games[] array (schema 1).
Rectangle {
    id: card
    required property var modelData
    property bool selected: false
    signal chosen()
    signal launchRequested()

    readonly property var game: modelData
    readonly property bool launchable: game.launchable === true

    radius: 16
    color: selected ? Theme.cardSelected : (hover.containsMouse ? Theme.cardHover : Theme.card)
    border.width: selected ? 2 : 1
    border.color: selected ? Theme.accent : Theme.line

    Behavior on color { ColorAnimation { duration: 120 } }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: card.chosen()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            StatusPill {
                label: Theme.publisherLabel(card.game.publisher_status)
                tint: Theme.publisherColor(card.game.publisher_status)
            }
            Item { Layout.fillWidth: true }
            Text {
                text: card.game.runner === "proton" ? "Proton" : "Wine"
                color: Theme.muted
                font.pixelSize: 12
            }
        }

        Text {
            Layout.fillWidth: true
            text: card.game.name
            color: Theme.text
            font.pixelSize: 19
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }

        Text {
            Layout.fillWidth: true
            text: card.game.anticheat === "none" ? "No anti-cheat" : "Anti-cheat: " + card.game.anticheat.toUpperCase()
            color: Theme.muted
            font.pixelSize: 13
            elide: Text.ElideRight
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                width: 9; height: 9; radius: 4.5
                color: Theme.schedColor(card.game.scheduling.state)
            }
            Text {
                Layout.fillWidth: true
                text: Theme.schedLabel(card.game.scheduling.state)
                color: Theme.schedColor(card.game.scheduling.state)
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }

        // Launch when allowed; otherwise say why, in plain words.
        Rectangle {
            id: action
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: 10
            color: card.launchable ? (launchMouse.containsMouse ? Theme.accent : Theme.accentDeep) : "transparent"
            border.width: card.launchable ? 0 : 1
            border.color: Theme.disabled

            Text {
                anchors.centerIn: parent
                width: parent.width - 20
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                text: card.launchable ? "Launch" : Theme.humanRefusal(card.game.refusal)
                color: card.launchable ? "#06141a" : Theme.muted
                font.pixelSize: card.launchable ? 14 : 12
                font.weight: card.launchable ? Font.DemiBold : Font.Normal
            }

            MouseArea {
                id: launchMouse
                anchors.fill: parent
                enabled: card.launchable
                hoverEnabled: true
                cursorShape: card.launchable ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: card.launchRequested()
            }
        }
    }
}
