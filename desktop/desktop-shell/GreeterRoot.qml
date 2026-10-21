// Original OminX login screen host. Repository license applies.
// The themed panel is the shared OminX artwork; this root adds the
// keyboard-only power action so the screen is usable without a pointer.
import QtQuick
import QtQuick.Controls

Item {
    id: host
    width: 1440; height: 900
    Greeter { anchors.fill: parent }
    Shortcut {
        sequence: "Ctrl+Alt+End"
        onActivated: if (sddm && sddm.canPowerOff) sddm.powerOff()
    }
}
