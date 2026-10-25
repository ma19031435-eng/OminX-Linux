pragma Singleton
import QtQuick

// OminX Harbor palette and the plain-language labels for backend states.
// Labels map the stable JSON values from `ominx-win game list --json` to words
// a player understands. The JSON values never change; only the wording does.
QtObject {
    readonly property color background: "#0b1622"
    readonly property color sidebar: "#0e1a28"
    readonly property color card: "#13243a"
    readonly property color cardHover: "#183050"
    readonly property color cardSelected: "#1a3a52"
    readonly property color line: "#1f3a55"
    readonly property color accent: "#5fd3c1"
    readonly property color accentDeep: "#2a8f87"
    readonly property color amber: "#e8be60"
    readonly property color red: "#e87171"
    readonly property color text: "#e2ecf2"
    readonly property color muted: "#8fa4b4"
    readonly property color disabled: "#3b5165"

    function publisherLabel(status) {
        switch (status) {
        case "vendor-opt-in": return "Publisher enabled"
        case "pending": return "Awaiting publisher"
        case "denied": return "Blocked by publisher"
        default: return "No anti-cheat"
        }
    }

    function publisherColor(status) {
        switch (status) {
        case "vendor-opt-in": return accent
        case "pending": return amber
        case "denied": return red
        default: return muted
        }
    }

    function schedLabel(state) {
        switch (state) {
        case "ready": return "Boost ready: CPU, I/O, GPU"
        case "not-delegated": return "Boost unavailable in this session"
        default: return "Default priority"
        }
    }

    function schedColor(state) {
        switch (state) {
        case "ready": return accent
        case "not-delegated": return amber
        default: return muted
        }
    }

    function humanRefusal(reason) {
        switch (reason) {
        case "anticheat-denied": return "The publisher blocks Linux for this title."
        case "anticheat-pending-publisher-support": return "Waiting for the publisher to enable Linux."
        default:
            if (reason && reason.indexOf("eac-v2-requirements-unmet:") === 0)
                return "This computer is missing a Linux anti-cheat requirement."
            return reason ? "Not launchable: " + reason : ""
        }
    }
}
