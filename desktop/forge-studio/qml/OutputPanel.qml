pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Problems (diagnostics from `ominx-forge check --json`) and Output (the last command's text).
Rectangle {
    id: panel

    property var diagnostics: []
    property string outputText: ""
    property string statusLine: ""
    signal jumpRequested(string file, int line, int col)

    color: Theme.chrome

    function showOutput() {
        tabs.currentIndex = 1
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacing
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacing

            TabBar {
                id: tabs
                background: null
                Layout.preferredWidth: implicitWidth
                TabButton { text: "Problems (" + panel.diagnostics.length + ")" }
                TabButton { text: "Output" }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: panel.statusLine
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                elide: Text.ElideRight
                Layout.maximumWidth: 420
            }
        }

        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: problems
                clip: true
                model: panel.diagnostics
                spacing: 2
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    id: delegateItem
                    required property var modelData
                    width: problems.width
                    height: 26
                    onClicked: panel.jumpRequested(delegateItem.modelData.file, delegateItem.modelData.line, delegateItem.modelData.col)
                    contentItem: Text {
                        text: delegateItem.modelData.file + ":" + delegateItem.modelData.line + ":" + delegateItem.modelData.col + "  " + delegateItem.modelData.message
                        color: Theme.error
                        font.family: Theme.codeFont
                        font.pixelSize: 13
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: Theme.radius
                        color: delegateItem.hovered ? Theme.hover : "transparent"
                    }
                }
                Label {
                    anchors.centerIn: parent
                    visible: panel.diagnostics.length === 0
                    text: "No problems."
                    color: Theme.muted
                    font.family: Theme.uiFont
                }
            }

            ScrollView {
                clip: true
                TextArea {
                    readOnly: true
                    selectByMouse: true
                    text: panel.outputText
                    color: Theme.text
                    font.family: Theme.codeFont
                    font.pixelSize: 13
                    background: null
                    wrapMode: TextEdit.NoWrap
                }
            }
        }
    }
}
