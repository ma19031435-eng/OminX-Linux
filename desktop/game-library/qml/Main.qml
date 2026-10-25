import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

// OminX Game Library.
// The host sets these inputs: gamesJson (the output of `ominx-win game list --json`),
// serviceState ("ready", "preparing" or "stopped"), and gamesDir (where profile icons
// live). It also provides a `bridge` object with launch(id). Nothing here runs a command.
//
// The window is frameless: TitleBar draws minimize, maximize and close, as every
// OminX app does. The page has one search field and no navigation chrome.
ApplicationWindow {
    id: window
    width: 1200
    height: 760
    minimumWidth: 900
    minimumHeight: 560
    visible: true
    title: "OminX Game Library"
    color: Theme.background
    flags: Qt.Window | Qt.FramelessWindowHint

    property string gamesJson: typeof initialGames === "string" ? initialGames : "{\"schema\":1,\"games\":[]}"
    property string serviceState: typeof initialService === "string" ? initialService : "ready"
    property string gamesDir: typeof initialGamesDir === "string" ? initialGamesDir : "/usr/share/ominx/games"
    property string selectedId: ""
    property string filter: ""
    property var allGames: []
    readonly property var visibleGames: applyFilter(allGames, filter)
    readonly property int visibleCount: visibleGames.length
    readonly property var selectedGame: findGame(selectedId)
    readonly property int schemaVersion: parsedSchema

    // Shown when nothing is selected, so the detail panel never reads null fields.
    readonly property var blankGame: ({ name: "", runner: "", anticheat: "none", publisher_status: "none",
                                        launchable: false, refusal: "", program: "", notes: "", icon: "",
                                        requires: "none", scheduling: { state: "", detail: "" } })

    property int parsedSchema: 0

    onGamesJsonChanged: parseGames()
    Component.onCompleted: parseGames()

    // Escape clears the selection, the same as clicking empty space.
    Shortcut {
        sequence: "Escape"
        onActivated: window.selectedId = ""
    }

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

    TitleBar {
        id: titleBar
        appWindow: window
        title: "OminX Game Library"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
    }

    // Header: heading, a one-line status, and the search field.
    RowLayout {
        id: header
        anchors.top: titleBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 28
        anchors.rightMargin: 28
        anchors.topMargin: 22
        spacing: 16

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: "Games"
                color: Theme.text
                font.pixelSize: 26
                font.weight: Font.DemiBold
            }
            Text {
                text: window.visibleCount + (window.visibleCount === 1 ? " title" : " titles")
                      + "  \u00b7  Windows service " + (window.serviceState === "ready" ? "ready" : window.serviceState)
                color: Theme.muted
                font.pixelSize: 12
            }
        }

        TextField {
            id: search
            Layout.preferredWidth: 240
            Layout.preferredHeight: 36
            placeholderText: "Search"
            color: Theme.text
            placeholderTextColor: Theme.muted
            selectByMouse: true
            leftPadding: 12
            rightPadding: 12
            background: Rectangle {
                radius: 10
                color: Theme.card
                border.width: search.activeFocus ? 1 : 0
                border.color: Theme.accent
            }
            onTextChanged: window.filter = text
        }
    }

    // Body: the grid, and the detail panel that appears when a title is selected.
    RowLayout {
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 18
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // Clicking empty space clears the selection.
            MouseArea {
                anchors.fill: parent
                onClicked: window.selectedId = ""
            }

            GridView {
                id: grid
                anchors.fill: parent
                anchors.leftMargin: 22
                anchors.rightMargin: 12
                anchors.bottomMargin: 12
                clip: true
                model: window.visibleGames
                cellWidth: 200
                cellHeight: 214
                boundsBehavior: Flickable.StopAtBounds

                delegate: GameCard {
                    width: grid.cellWidth - 14
                    height: grid.cellHeight - 14
                    iconBase: window.gamesDir
                    selected: window.selectedId === modelData.id
                    onChosen: window.selectedId = modelData.id
                }

                Text {
                    anchors.centerIn: parent
                    visible: window.visibleCount === 0
                    text: window.allGames.length === 0 ? "No games yet." : "No games match that search."
                    color: Theme.muted
                    font.pixelSize: 14
                }
            }
        }

        DetailPanel {
            id: detail
            visible: window.selectedGame !== null
            Layout.preferredWidth: visible ? 320 : 0
            Layout.fillHeight: true
            game: window.selectedGame !== null ? window.selectedGame : window.blankGame
            iconBase: window.gamesDir
            onLaunchRequested: window.launch(window.selectedId)
        }
    }

    // Resize grip for the frameless window.
    MouseArea {
        width: 16; height: 16
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeFDiagCursor
        onPressed: window.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
    }
}
