// Original OminX artwork and theme. Repository license applies.
// Real SDDM context APIs own authentication and session/power operations.
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "ominxGreeter"
    width: 1440; height: 900
    color: "#101d32"
    property bool busy: false
    readonly property bool passwordIsMasked: password.echoMode === TextInput.Password
    property string failure: ""
    property string powerAction: ""
    property date clock: new Date()
    readonly property bool compact: height < 760
    readonly property color accent: "#74e0c7"
    readonly property bool caps: typeof keyboard !== "undefined" && keyboard.capsLock
    component QuietButton: Button {
        id: quietButton
        implicitWidth: 104; implicitHeight: 36
        contentItem: Text {
            text: quietButton.text; color: "#e5f0f2"; font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 9; color: quietButton.hovered ? "#294b57" : "#17333f"
            border.color: quietButton.activeFocus ? root.accent : "#4a6d77"
        }
    }
    function login() {
        if (busy) return
        if (username.text.trim().length === 0) {
            failure = qsTr("Enter your username.")
            username.forceActiveFocus()
            return
        }
        if (session.currentIndex < 0) {
            failure = qsTr("No desktop session is installed.")
            return
        }
        failure = ""
        busy = true
        sddm.login(username.text.trim(), password.text, session.currentIndex)
    }
    function resetFailure() {
        busy = false
        failure = qsTr("Sign-in failed. Check your username and password.")
        password.text = ""
        password.forceActiveFocus()
    }
    Timer { interval: 1000; repeat: true; running: true; onTriggered: root.clock = new Date() }
    Connections {
        target: sddm
        function onLoginFailed() { root.resetFailure() }
        function onLoginSucceeded() { password.text = ""; root.failure = "" }
    }
    gradient: Gradient {
        GradientStop { position: 0; color: "#12213a" }
        GradientStop { position: 0.7; color: "#123d46" }
        GradientStop { position: 1; color: "#102630" }
    }
    Canvas {
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset()
            var w = width, h = height
            var g = c.createLinearGradient(0, h, w, 0)
            g.addColorStop(0, "#267d7b"); g.addColorStop(1, "#244767")
            c.fillStyle = g
            c.beginPath(); c.moveTo(0, h * 0.83)
            c.bezierCurveTo(w * 0.30, h * 0.83, w * 0.24, h * 0.14, w * 0.53, 0)
            c.lineTo(w * 0.66, 0)
            c.bezierCurveTo(w * 0.35, h * 0.36, w * 0.48, h * 0.92, w, h * 0.80)
            c.lineTo(w, h); c.lineTo(0, h); c.closePath(); c.fill()
            c.strokeStyle = "#437c8a"; c.lineWidth = 1
            for (var i = 0; i < 8; i++) {
                c.beginPath(); c.moveTo(w * 0.64 + i * 17, 0)
                c.bezierCurveTo(w * 0.33 + i * 18, h * 0.36, w * 0.48 + i * 20, h * 1.01, w, h * 0.84 + i * 10)
                c.stroke()
            }
        }
    }
    Row {
        anchors.top: parent.top; anchors.left: parent.left
        anchors.margins: root.compact ? 22 : 40
        spacing: 12
        Rectangle {
            width: 28; height: 28; radius: 8; color: root.accent
            Text { anchors.centerIn: parent; text: "X"; font.pixelSize: 19; font.bold: true; color: "#112d35" }
        }
        Text { text: "OminX"; color: "#eff9f7"; font.pixelSize: 24; font.weight: Font.DemiBold }
    }
    Column {
        anchors.top: parent.top; anchors.right: parent.right
        anchors.margins: root.compact ? 22 : 40
        spacing: 3
        Text { anchors.right: parent.right; text: Qt.formatTime(root.clock, "hh:mm"); color: "#edf7f7"; font.pixelSize: 24 }
        Text { anchors.right: parent.right; text: Qt.formatDate(root.clock, "dddd, d MMMM"); color: "#b1c7cd"; font.pixelSize: 13 }
    }
    Rectangle {
        id: panel
        objectName: "loginPanel"
        width: Math.min(410, root.width - 32)
        height: form.implicitHeight + (root.compact ? 36 : 56)
        anchors.centerIn: parent
        anchors.verticalCenterOffset: root.compact ? 12 : 0
        radius: 26; color: "#eb122532"
        border.width: 1; border.color: "#41606a"
        ColumnLayout {
            id: form
            anchors.centerIn: parent
            width: parent.width - 56
            spacing: root.compact ? 10 : 15
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                width: root.compact ? 56 : 72; height: width; radius: width / 2
                color: "#254652"; border.color: "#4d827f"
                Text {
                    anchors.centerIn: parent
                    text: username.text.trim().length ? username.text.trim().charAt(0).toUpperCase() : "O"
                    font.pixelSize: root.compact ? 25 : 31; color: root.accent
                }
            }
            Text { Layout.alignment: Qt.AlignHCenter; text: qsTr("Welcome back"); color: "#f2f9fa"; font.pixelSize: 27; font.weight: Font.DemiBold }
            Text { Layout.alignment: Qt.AlignHCenter; text: qsTr("Your space. Ready when you are."); color: "#afc5cd"; font.pixelSize: 13 }
            TextField {
                id: username; objectName: "username"
                Layout.fillWidth: true; implicitHeight: 44
                text: userModel ? userModel.lastUser : ""; placeholderText: qsTr("Username")
                enabled: !root.busy; color: "#f1f7f9"; font.pixelSize: 15
                selectByMouse: true; placeholderTextColor: "#9bb3bd"
                Accessible.name: qsTr("Username")
                background: Rectangle { radius: 10; color: "#10212d"; border.width: 1; border.color: username.activeFocus ? root.accent : "#3c5664" }
                onAccepted: password.forceActiveFocus()
            }
            TextField {
                id: password; objectName: "password"
                Layout.fillWidth: true; implicitHeight: 44
                placeholderText: qsTr("Password"); placeholderTextColor: "#9bb3bd"; echoMode: TextInput.Password
                enabled: !root.busy; color: "#f1f7f9"; font.pixelSize: 15
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText
                Accessible.name: qsTr("Password")
                background: Rectangle { radius: 10; color: "#10212d"; border.width: 1; border.color: password.activeFocus ? root.accent : "#3c5664" }
                onAccepted: root.login()
                Keys.onEscapePressed: { password.text = ""; if (!root.busy) root.failure = "" }
            }
            Text {
                objectName: "capsWarning"
                Layout.fillWidth: true; visible: root.caps
                text: qsTr("Caps Lock is on"); color: "#ffd394"; font.pixelSize: 12
            }
            ComboBox {
                id: session; objectName: "session"
                Layout.fillWidth: true; implicitHeight: 38
                model: sessionModel; textRole: "name"; currentIndex: sessionModel ? sessionModel.lastIndex : -1
                enabled: !root.busy
                Accessible.name: qsTr("Desktop session")
                contentItem: Text { text: session.displayText; color: "#cad9df"; verticalAlignment: Text.AlignVCenter; leftPadding: 12; rightPadding: 25; elide: Text.ElideRight; font.pixelSize: 13 }
                background: Rectangle { radius: 9; color: "#142d3b"; border.color: session.activeFocus ? root.accent : "#365462" }
            }
            Button {
                id: submit; objectName: "signIn"
                Layout.fillWidth: true; implicitHeight: 45
                enabled: !root.busy
                text: root.busy ? qsTr("Signing in…") : qsTr("Sign in")
                Accessible.name: text
                contentItem: Text { text: submit.text; color: "#102e34"; font.weight: Font.DemiBold; font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 10; color: submit.down ? "#4fbba5" : submit.hovered ? "#9eefd9" : root.accent; border.width: submit.activeFocus ? 2 : 0; border.color: "white" }
                onClicked: root.login()
            }
            Text {
                objectName: "loginError"
                Layout.fillWidth: true; visible: root.failure.length > 0
                text: root.failure; color: "#ffb3ac"; font.pixelSize: 12
                wrapMode: Text.WordWrap
                Accessible.role: Accessible.AlertMessage
                Accessible.name: text
            }
        }
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: root.compact ? 12 : 30
        spacing: 12
        QuietButton {
            objectName: "restartButton"
            text: qsTr("Restart"); enabled: !root.busy && sddm && sddm.canReboot
            onClicked: { root.powerAction = "reboot"; confirmation.open() }
        }
        QuietButton {
            objectName: "shutdownButton"
            text: qsTr("Shut down"); enabled: !root.busy && sddm && sddm.canPowerOff
            onClicked: { root.powerAction = "poweroff"; confirmation.open() }
        }
    }
    Dialog {
        id: confirmation; objectName: "powerConfirmation"
        anchors.centerIn: parent; modal: true
        title: root.powerAction === "reboot" ? qsTr("Restart this computer?") : qsTr("Shut down this computer?")
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            if (root.powerAction === "reboot") sddm.reboot()
            else if (root.powerAction === "poweroff") sddm.powerOff()
            root.powerAction = ""
        }
        onRejected: root.powerAction = ""
    }
    Component.onCompleted: {
        if (username.text.trim().length) password.forceActiveFocus()
        else username.forceActiveFocus()
    }
}
