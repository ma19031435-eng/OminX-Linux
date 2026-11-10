import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

// Forge Studio: the project window for Forge apps on OminXOS.
// Every toolchain action goes through the `forge` bridge object, which runs fixed
// `ominx-forge` operations (see host/forge_bridge.py). The QML never builds commands.
// The open file is saved before switching files, checking, running, testing or building,
// so the tools always see what the editor shows.
ApplicationWindow {
    id: window

    width: 1220
    height: 780
    minimumWidth: 920
    minimumHeight: 560
    visible: true
    title: (editor.path ? editor.path + (editor.dirty ? " •" : "") + " — " : "") + "Forge Studio"
    color: Theme.navy

    // ----- project state -----
    property string projectDir: ""
    property var entries: []
    property var diagnostics: []
    property string outputText: ""
    property string statusLine: "Open a project folder to begin."
    property int requestSeq: 0
    property int pending: 0
    readonly property bool busy: pending > 0

    // What to do after the next successful save: "open:<rel>", an operation name, or "".
    property string afterSave: ""
    property string pendingOpen: ""
    property string pendingNewFolder: ""
    property var pendingJump: null

    function send(op, dir, rel, content) {
        requestSeq += 1
        pending += 1
        // qmllint disable unqualified
        forge.request(String(requestSeq), op, dir, rel || "", content || "")
    }

    function request(op) {
        send(op, projectDir, "", "")
    }

    function openProject(path) {
        const folder = path.trim()
        if (folder.length === 0) return
        projectDir = folder
        editor.path = ""
        editor.loadText("")
        diagnostics = []
        outputText = ""
        request("tree")
    }

    function openFile(rel) {
        if (editor.dirty && editor.path) {
            afterSave = "open:" + rel
            send("write", projectDir, editor.path, editor.text)
            return
        }
        pendingOpen = rel
        send("read", projectDir, rel, "")
    }

    // Save the open file (when it has changes), then run the action.
    function runAction(op) {
        if (projectDir === "") return
        if (editor.dirty && editor.path) {
            afterSave = op
            send("write", projectDir, editor.path, editor.text)
        } else {
            request(op)
        }
    }

    function parseJson(text) {
        try {
            return JSON.parse(text)
        } catch (e) {
            return null
        }
    }

    // Distinct files that have problems, as the navigator shows them.
    function problemFileList() {
        const seen = {}
        const files = []
        for (let i = 0; i < diagnostics.length; i++) {
            const f = diagnostics[i].file
            if (!seen[f]) {
                seen[f] = true
                files.push(f)
            }
        }
        return files
    }

    function showProblems(data) {
        diagnostics = (data && data.diagnostics) ? data.diagnostics : []
        statusLine = diagnostics.length === 0 ? "No problems" : diagnostics.length + " problem(s)"
    }

    // qmllint disable unqualified
    Connections {
        target: forge
        function onFinished(requestId, op, ok, exitCode, stdout, stderr, dataJson) {
            window.pending = Math.max(0, window.pending - 1)
            const errorText = stderr.trim() || ("exit " + exitCode)

            if (op === "tree") {
                if (!ok) {
                    window.statusLine = errorText
                    return
                }
                window.entries = window.parseJson(dataJson) || []
                window.statusLine = "Project loaded"
                window.request("check")
                for (let i = 0; i < window.entries.length; i++) {
                    if (window.entries[i].path === "src/main.fg") {
                        window.openFile("src/main.fg")
                        break
                    }
                }
            } else if (op === "read") {
                if (ok) {
                    editor.path = window.pendingOpen
                    editor.loadText(stdout)
                    window.statusLine = "Opened " + window.pendingOpen
                } else {
                    window.statusLine = errorText
                }
                window.pendingOpen = ""
            } else if (op === "write") {
                const next = window.afterSave
                window.afterSave = ""
                if (!ok) {
                    window.statusLine = errorText
                    return
                }
                editor.dirty = false
                window.statusLine = "Saved " + editor.path
                if (next.startsWith("open:")) {
                    window.openFile(next.substring(5))
                } else if (next !== "") {
                    window.request(next)
                } else {
                    window.request("check")
                }
            } else if (op === "check") {
                window.showProblems(window.parseJson(dataJson))
            } else if (op === "new") {
                if (!ok) {
                    window.statusLine = errorText
                    return
                }
                window.statusLine = "Created " + window.pendingNewFolder
                window.openProject(window.pendingNewFolder)
            } else {
                // run, test, build
                const body = stdout + (stderr ? (stdout ? "\n" : "") + stderr : "")
                window.outputText = body.length ? body : "(no output)"
                if (op === "build" && ok) {
                    window.statusLine = "Built " + stdout.trim()
                } else {
                    window.statusLine = (ok ? "" : "Failed: ") + op + (ok ? " finished" : " (" + errorText + ")")
                }
                bottom.showOutput()
            }
        }
    }

    Shortcut { sequence: "Ctrl+S"; onActivated: window.runAction("check") }
    Shortcut { sequence: "Ctrl+R"; onActivated: window.runAction("run") }
    Shortcut { sequence: "Ctrl+T"; onActivated: window.runAction("test") }
    Shortcut { sequence: "Ctrl+B"; onActivated: window.runAction("build") }

    NewProjectDialog {
        id: newDialog
        onCreateRequested: (folder, ident, name) => {
            window.pendingNewFolder = folder
            window.send("new", folder, ident, name)
        }
    }

    header: Rectangle {
        height: 52
        color: Theme.chrome

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: Theme.spacing

            Text {
                text: "Forge Studio"
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 16
                font.bold: true
            }

            TextField {
                id: pathField
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                placeholderText: "Project folder, for example /home/ominx/Forge/PuzzleGarden"
                placeholderTextColor: Theme.muted
                text: window.projectDir
                color: Theme.text
                background: Rectangle {
                    color: Theme.gutter
                    border.color: pathField.activeFocus ? Theme.accent : Theme.line
                    border.width: 1
                    radius: 4
                }
                font.family: Theme.codeFont
                font.pixelSize: 13
                selectByMouse: true
                onAccepted: window.openProject(text)
            }

            ForgeButton {
                text: "Open"
                onClicked: window.openProject(pathField.text)
            }
            ForgeButton {
                text: "New project…"
                onClicked: newDialog.open()
            }

            Item { Layout.fillWidth: true }

            ForgeButton {
                text: "Check"
                enabled: window.projectDir !== "" && !window.busy
                onClicked: window.runAction("check")
            }
            ForgeButton {
                text: "Test"
                enabled: window.projectDir !== "" && !window.busy
                onClicked: window.runAction("test")
            }
            ForgeButton {
                text: "Build .opkgx"
                enabled: window.projectDir !== "" && !window.busy
                onClicked: window.runAction("build")
            }
            ForgeButton {
                text: "Run"
                highlighted: true
                enabled: window.projectDir !== "" && !window.busy
                onClicked: window.runAction("run")
            }
        }
    }

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        Navigator {
            SplitView.preferredWidth: 240
            SplitView.minimumWidth: 180
            entries: window.entries
            currentPath: editor.path
            problemFiles: window.problemFileList()
            onOpenRequested: (path) => window.openFile(path)
        }

        SplitView {
            orientation: Qt.Vertical
            SplitView.fillWidth: true

            Editor {
                id: editor
                SplitView.fillHeight: true
                SplitView.minimumHeight: 200
            }

            OutputPanel {
                id: bottom
                SplitView.preferredHeight: 210
                SplitView.minimumHeight: 110
                diagnostics: window.diagnostics
                outputText: window.outputText
                statusLine: window.statusLine
                onJumpRequested: (file, line, col) => {
                    const target = file.startsWith("src/") || file === "forge.project" ? file : "src/" + file
                    if (target === editor.path) {
                        editor.gotoLine(line, col)
                    } else {
                        window.pendingJump = { line: line, col: col }
                        window.openFile(target)
                    }
                }
            }
        }
    }

    Connections {
        target: editor
        function onPathChanged() {
            if (window.pendingJump && editor.path !== "") {
                editor.gotoLine(window.pendingJump.line, window.pendingJump.col)
                window.pendingJump = null
            }
        }
    }

    footer: Rectangle {
        height: 26
        color: Theme.chrome

        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 14
            width: parent.width - 28
            text: window.busy ? "Working…" : window.statusLine
            color: Theme.muted
            font.family: Theme.uiFont
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }
}
