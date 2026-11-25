pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Project tree. Each entry is {path, kind} from `ominx-forge tree <dir> --json`.
Rectangle {
    id: nav

    property var entries: []
    property string currentPath: ""
    property var problemFiles: []
    signal openRequested(string path)

    color: Theme.chrome

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacing
        spacing: 4

        Label {
            text: "PROJECT"
            color: Theme.muted
            font.family: Theme.uiFont
            font.pixelSize: 11
            font.letterSpacing: 1.2
            Layout.fillWidth: true
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: nav.entries
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: ItemDelegate {
                id: row
                required property var modelData
                readonly property bool isDir: row.modelData.kind === "dir"
                readonly property bool isCurrent: row.modelData.path === nav.currentPath
                readonly property int depth: (row.modelData.path.match(/\//g) || []).length
                width: list.width
                height: 28
                leftPadding: 8 + depth * 14
                highlighted: isCurrent
                enabled: !isDir
                onClicked: nav.openRequested(row.modelData.path)

                contentItem: RowLayout {
                    spacing: 6
                    Text {
                        text: row.isDir ? "▸" : (row.modelData.path === "forge.project" ? "■" : "•")
                        color: row.isDir ? Theme.muted : Theme.accent
                        font.pixelSize: 11
                        Layout.preferredWidth: 10
                    }
                    Text {
                        text: row.modelData.path.split("/").pop()
                        color: row.isDir ? Theme.muted : Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: 13
                        font.bold: row.isCurrent
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Rectangle {
                        visible: !row.isDir && nav.problemFiles.indexOf(row.modelData.path) >= 0
                        width: 7
                        height: 7
                        radius: 4
                        color: Theme.error
                    }
                }

                background: Rectangle {
                    radius: Theme.radius
                    color: row.isCurrent ? Theme.selection : (row.hovered && !row.isDir ? Theme.hover : "transparent")
                }
            }
        }

        Label {
            visible: nav.entries.length === 0
            text: "Open a project folder to see its files."
            color: Theme.muted
            wrapMode: Text.WordWrap
            font.family: Theme.uiFont
            font.pixelSize: 12
            Layout.fillWidth: true
        }
    }
}
