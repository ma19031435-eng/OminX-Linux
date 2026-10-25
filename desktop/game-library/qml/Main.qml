import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// OminX Game Library.
// The host sets two inputs: gamesJson (the output of `ominx-win game list --json`)
// and serviceState ("ready", "preparing", or "stopped"). It also provides a
// `bridge` object with launch(id). Nothing here runs a command itself.
ApplicationWindow {
    id: window
    width: 1280
    height: 820
    minimumWidth: 980
    minimumHeight: 620
    visible: true
    title: "OminX Game Library"
    color: Theme.background

    property string gamesJson: typeof initialGames === "string" ? initialGames : "{\"schema\":1,\"games\":[]}"
    property string serviceState: typeof initialService === "string" ? initialService : "ready"
    property string selectedId: ""
    property string filter: ""
    property var allGames: []
    readonly property var visibleGames: applyFilter(allGames, filter)
    readonly property int visibleCount: visibleGames.length
    readonly property var selectedGame: findGame(selectedId)
    readonly property int schemaVersion: parsedSchema

    property int parsedSchema: 0

    onGamesJsonChanged: parseGames()
    Component.onCompleted: parseGames()

    function parseGames() {
        var data = JSON.parse(gamesJson)
        parsedSchema = data.schema || 0
        // Profiles that failed validation are listed by the backend but are not shown as titles.
        allGames = (data.games || []).filter(function (g) { return g.valid === true })
    }

    function applyFilter(games, text) {
        var needle = text.trim().toLowerCase()
        if (needle.length === 0) return games
        return games.filter(function (g) { return g.name.toLowerCase().indexOf(needle) >= 0 })
    }

    function findGame(id) {
        for (var i = 0; i < allGames.length; i++)
            if (allGames[i].id === id) return allGames[i]
        return null
    }

    function launch(id) {
        // Enforce the gate here too: only titles the CLI marked launchable can be sent.
        var g = findGame(id)
        if (!g || g.launchable !== true) return
        if (typeof bridge !== "undefined" && bridge) bridge.launch(id)
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Sidebar
        Rectangle {
            Layout.preferredWidth: 224
            Layout.fillHeight: true
            color: Theme.sidebar

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 22
                spacing: 6

                RowLayout {
                    Layout.bottomMargin: 26
                    spacing: 12
                    Rectangle {
                        width: 34; height: 34; radius: 10
                        gradient: Gradient {
                            GradientStop { position: 0; color: Theme.accent }
                            GradientStop { position: 1; color: Theme.accentDeep }
                        }
                        Text { anchors.centerIn: parent; text: "O"; color: "#06141a"; font.pixelSize: 17; font.weight: Font.Black }
                    }
                    ColumnLayout {
                        spacing: 0
                        Text { text: "OminX"; color: Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold }
                        Text { text: "Harbor"; color: Theme.muted; font.pixelSize: 11 }
                    }
                }

                Repeater {
                    model: [
                        { label: "Library", key: "library", enabled: true },
                        { label: "Scheduling", key: "scheduling", enabled: false },
                        { label: "Windows programs", key: "programs", enabled: false },
                        { label: "Settings", key: "settings", enabled: false }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 10
                        color: modelData.key === "library" ? Theme.card : "transparent"
                        Rectangle {
                            visible: modelData.key === "library"
                            width: 3; height: 20; radius: 2
                            color: Theme.accent
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 18
                            text: modelData.label
                            color: modelData.enabled ? Theme.text : Theme.disabled
                            font.pixelSize: 14
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    radius: 12
                    color: Theme.card
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 10
                        Rectangle {
                            width: 9; height: 9; radius: 4.5
                            color: window.serviceState === "ready" ? Theme.accent
                                 : (window.serviceState === "preparing" ? Theme.amber : Theme.red)
                        }
                        ColumnLayout {
                            spacing: 0
                            Text { text: "Windows service"; color: Theme.text; font.pixelSize: 12 }
                            Text {
                                text: window.serviceState.charAt(0).toUpperCase() + window.serviceState.slice(1)
                                color: Theme.muted
                                font.pixelSize: 11
                            }
                        }
                    }
                }
            }
        }

        // Main column
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 104
                color: "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 32
                    anchors.rightMargin: 32
                    spacing: 20

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Text {
                            text: "Game Library"
                            color: Theme.text
                            font.pixelSize: 28
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: "Compatibility and scheduling for every title on this computer"
                            color: Theme.muted
                            font.pixelSize: 13
                        }
                    }

                    TextField {
                        id: search
                        Layout.preferredWidth: 220
                        Layout.preferredHeight: 40
                        placeholderText: "Search titles"
                        color: Theme.text
                        placeholderTextColor: Theme.muted
                        font.pixelSize: 14
                        leftPadding: 14
                        rightPadding: 14
                        onTextChanged: window.filter = text
                        background: Rectangle {
                            radius: 12
                            color: Theme.card
                            border.width: search.activeFocus ? 2 : 1
                            border.color: search.activeFocus ? Theme.accent : Theme.line
                        }
                    }
                }
            }

            GridView {
                id: grid
                Layout.fillWidth: true
                Layout.fillHeight: true
                leftMargin: 32
                topMargin: 4
                clip: true
                cellWidth: 316
                cellHeight: 224
                model: window.visibleGames
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Item {
                    required property var modelData
                    width: grid.cellWidth
                    height: grid.cellHeight
                    GameCard {
                        anchors.fill: parent
                        anchors.margins: 8
                        modelData: parent.modelData
                        selected: window.selectedId === modelData.id
                        onChosen: window.selectedId = modelData.id
                        onLaunchRequested: window.launch(modelData.id)
                    }
                }

                Text {
                    anchors.centerIn: parent
                    visible: grid.count === 0
                    text: window.allGames.length === 0 ? "No titles are installed yet." : "No titles match \"" + window.filter + "\"."
                    color: Theme.muted
                    font.pixelSize: 15
                }
            }

            // Status footer
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                color: Theme.sidebar
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 32
                    anchors.rightMargin: 32
                    Text {
                        text: window.visibleCount + (window.visibleCount === 1 ? " title" : " titles")
                        color: Theme.muted
                        font.pixelSize: 12
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: "Game data schema " + window.schemaVersion
                        color: Theme.muted
                        font.pixelSize: 12
                    }
                }
            }
        }

        DetailPanel {
            Layout.preferredWidth: window.selectedGame ? 360 : 0
            Layout.fillHeight: true
            visible: window.selectedGame !== null
            game: window.selectedGame
            onCloseRequested: window.selectedId = ""
            onLaunchRequested: function (id) { window.launch(id) }
        }
    }
}
