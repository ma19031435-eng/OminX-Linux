import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Creates a project with `ominx-forge new`. The folder must not exist yet; the CLI checks that.
Dialog {
    id: dialog

    signal createRequested(string folder, string ident, string name)

    title: "New Forge project"
    modal: true
    standardButtons: Dialog.Cancel | Dialog.Ok
    width: 520
    closePolicy: Popup.CloseOnEscape

    readonly property bool valid: folderField.text.trim().startsWith("/")
        && identField.text.trim().length > 0
        && nameField.text.trim().length > 0

    onOpened: {
        folderField.text = ""
        identField.text = ""
        nameField.text = ""
        folderField.forceActiveFocus()
    }

    onAccepted: {
        if (valid) createRequested(folderField.text.trim(), identField.text.trim(), nameField.text.trim())
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.panel
        border.color: Theme.line
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacing

        Label {
            text: "Folder (absolute path, must not exist yet)"
            color: Theme.muted
            font.family: Theme.uiFont
        }
        TextField {
            id: folderField
            Layout.fillWidth: true
            placeholderText: "/home/ominx/Forge/PuzzleGarden"
            font.family: Theme.codeFont
            color: Theme.text
            selectByMouse: true
        }

        Label {
            text: "App ID (reverse-DNS, for example org.example.puzzle)"
            color: Theme.muted
            font.family: Theme.uiFont
        }
        TextField {
            id: identField
            Layout.fillWidth: true
            placeholderText: "org.example.puzzle"
            font.family: Theme.codeFont
            color: Theme.text
            selectByMouse: true
        }

        Label {
            text: "Name"
            color: Theme.muted
            font.family: Theme.uiFont
        }
        TextField {
            id: nameField
            Layout.fillWidth: true
            placeholderText: "Puzzle Garden"
            color: Theme.text
            font.family: Theme.uiFont
            selectByMouse: true
        }
    }
}
