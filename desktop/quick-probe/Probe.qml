import QtQuick
import QtQuick.Controls

Item {
    width: 1280; height: 800
    Greeter { anchors.fill: parent }
    Rectangle {
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.margins: 8
        width: 255; height: 46; color: "#51242a"; radius: 6
        Text {
            anchors.centerIn: parent
            text: "GRAPHICS VALIDATION ONLY\nNo authentication or desktop session"
            color: "white"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter
        }
    }
}
