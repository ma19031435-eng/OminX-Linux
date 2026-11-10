pragma Singleton
import QtQuick

// OminX Harbor palette and the plain-language labels for backend states.
// Labels map the stable JSON values from `ominx-win game list --json` to words
// a player understands. The JSON values never change; only the wording does.
QtObject {
    // OminX brand palette: Deep Navy, Ocean Teal, Dark Cyan, Slate Blue, Soft White.
    readonly property color navy: "#101d32"
    readonly property color teal: "#74e0c7"
    readonly property color darkCyan: "#123d46"
    readonly property color slate: "#244767"
    readonly property color softWhite: "#eff9f7"

    readonly property color background: navy
    readonly property color chrome: "#0c1728"
    readonly property color card: "#15294a"
    readonly property color cardHover: "#1b3558"
    readonly property color cardSelected: darkCyan
    readonly property color hover: "#1b3558"
    readonly property color line: "#24466a"
    readonly property color accent: teal
    readonly property color accentDeep: "#4fbfa8"
    readonly property color amber: "#e8be60"
    readonly property color red: "#e87171"
    readonly property color closeRed: "#c42b1c"
    readonly property color text: softWhite
    readonly property color muted: "#9fb6c6"
    readonly property color disabled: "#3d5a78"

    // Monogram tile colours when a title has no icon file. Chosen per runner.
    function tileColor(runner) {
        return runner === "proton" ? "#24506b" : "#4a3d6b"
    }

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
