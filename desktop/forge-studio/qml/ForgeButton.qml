import QtQuick
import QtQuick.Controls

// Button in the OminX palette. Used everywhere in Forge Studio instead of the default style.
Button {
    id: control
    implicitHeight: 30
    leftPadding: 12
    rightPadding: 12
    font.family: Theme.uiFont
    font.pixelSize: 13
    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? (control.down ? Theme.navy : Theme.text) : Theme.muted
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 4
        color: !control.enabled ? Theme.chrome
             : control.down ? Theme.accent
             : control.hovered ? Theme.hover
             : Theme.slate
        border.color: control.visualFocus ? Theme.accent : Theme.line
        border.width: 1
    }
}
