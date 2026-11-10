pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Source editor for one .fg or project file. Wrapping is off so each gutter number
// lines up with exactly one text line. The gutter follows the scroll bar.
Rectangle {
    id: editor

    property string path: ""
    property alias text: area.text
    property bool dirty: false
    readonly property int lineCount: area.text.split("\n").length

    color: Theme.navy

    TextMetrics {
        id: metrics
        font: area.font
        text: "M"
    }

    // Scroll offset in pixels, from the vertical scroll bar.
    readonly property real scrollOffset: scroll.ScrollBar.vertical.position * Math.max(0, area.height - scroll.availableHeight)

    function gotoLine(line, column) {
        const lines = area.text.split("\n")
        const target = Math.max(1, Math.min(line, lines.length))
        let offset = 0
        for (let i = 0; i < target - 1; i++)
            offset += lines[i].length + 1
        const col = Math.max(1, column || 1)
        area.cursorPosition = Math.min(area.text.length, offset + col - 1)
        area.forceActiveFocus()
        const span = Math.max(1, area.height - scroll.availableHeight)
        const wanted = Math.max(0, (target - 4) * metrics.height)
        scroll.ScrollBar.vertical.setPosition(Math.min(1, wanted / span))
    }

    function loadText(newText) {
        area.text = newText
        editor.dirty = false
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Line numbers, scrolled with the text.
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 56
            color: Theme.gutter
            clip: true

            Column {
                y: -editor.scrollOffset + area.topPadding
                width: parent.width - 10
                Repeater {
                    model: editor.lineCount
                    delegate: Text {
                        required property int index
                        width: parent.width
                        horizontalAlignment: Text.AlignRight
                        text: index + 1
                        color: index + 1 === area.currentLine ? Theme.accent : Theme.muted
                        font.family: Theme.codeFont
                        font.pixelSize: Theme.codeSize
                        height: metrics.height
                    }
                }
            }
        }

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true

            TextArea {
                id: area
                property int currentLine: text.substring(0, cursorPosition).split("\n").length

                // Tall enough for every line, so the scroll bar covers the whole file.
                height: Math.max(implicitHeight, scroll.availableHeight)
                width: Math.max(implicitWidth, scroll.availableWidth)
                font.family: Theme.codeFont
                font.pixelSize: Theme.codeSize
                color: Theme.text
                selectionColor: Theme.slate
                selectedTextColor: Theme.text
                background: null
                wrapMode: TextEdit.NoWrap
                tabStopDistance: 4 * metrics.advanceWidth
                leftPadding: 12
                topPadding: 4
                selectByMouse: true
                persistentSelection: true

                onTextChanged: {
                    if (area.activeFocus) editor.dirty = true
                }
            }
        }
    }
}
