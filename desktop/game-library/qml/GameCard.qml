import QtQuick
import QtQuick.Layouts

// One title, shown as artwork and a name. The card selects; launching happens
// in the detail panel, so the grid carries no buttons. `game` is one entry of
// the backend's games[] array (schema 1).
Rectangle {
    id: card
    required property var modelData
    property string iconBase: ""
    property bool selected: false
    signal chosen()

    readonly property var game: modelData
    readonly property bool launchable: game.launchable === true
    readonly property bool hasIcon: game.icon !== undefined && game.icon !== "" && icon.status === Image.Ready

    radius: 14
    color: selected ? Theme.cardSelected : (hover.containsMouse ? Theme.cardHover : Theme.card)
    border.width: selected ? 2 : 0
    border.color: Theme.accent

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
        anchors.margins: 16
        spacing: 12

        // Artwork: the title's own icon when the profile has one, otherwise a
        // monogram tile. Blocked titles are dimmed so the state reads at a glance.
        Item {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 96
            Layout.preferredHeight: 96
            opacity: card.launchable ? 1.0 : 0.5

            Rectangle {
                anchors.fill: parent
                radius: 22
                color: Theme.tileColor(card.game.runner)
                visible: !card.hasIcon

                Text {
                    anchors.centerIn: parent
                    text: card.game.name.charAt(0).toUpperCase()
                    color: Theme.text
                    font.pixelSize: 40
                    font.weight: Font.Black
                }
            }

            Image {
                id: icon
                anchors.fill: parent
                source: (card.game.icon !== undefined && card.game.icon !== "" && card.iconBase !== "")
                        ? card.iconBase + "/" + card.game.icon : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: card.hasIcon
            }
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: card.game.name
            color: Theme.text
            font.pixelSize: 15
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: Theme.publisherLabel(card.game.publisher_status)
            color: Theme.publisherColor(card.game.publisher_status)
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }
}
