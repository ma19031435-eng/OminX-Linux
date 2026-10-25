#!/usr/bin/env python3
"""Host Qt 6 checks for the OminX Game Library QML, with real screenshots.

The window loads the fixture produced by `ominx-win game list --json`. The test
checks that the QML loads with no warnings, that search and selection work, and
that a blocked title never offers a launch. It then saves screenshots to
docs/previews/. Screenshots come from the real QML, rendered offscreen; they
show the Harbor styling, not a Plasma session.

Requires PySide6. Run with: make ui-check"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
import sys
from pathlib import Path

# Sandboxes without a GL/EGL/xkb/dbus runtime can point OMINX_QT_STUB_DIR at
# symbol-less stand-ins. Offscreen software rendering then never calls them.
# Real machines leave this unset and load the system libraries.
_stub_dir = os.environ.get('OMINX_QT_STUB_DIR')
if _stub_dir:
    import ctypes
    sys.setdlopenflags(os.RTLD_LAZY | os.RTLD_GLOBAL)
    for _name in ('libGL.so.1', 'libEGL.so.1', 'libxkbcommon.so.0', 'libdbus-1.so.3'):
        ctypes.CDLL(os.path.join(_stub_dir, _name), mode=ctypes.RTLD_GLOBAL)

from PySide6.QtCore import QObject, QUrl, Slot, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[2]
QML = ROOT / 'desktop/game-library/qml/Main.qml'
FIXTURE = ROOT / 'desktop/game-library/fixtures/games.json'
PREVIEWS = ROOT / 'docs/previews'

problems = []


def collect(kind, context, text):
    print(text, file=sys.stderr)
    if 'qrc:' in text or '.qml' in text or 'ReferenceError' in text or 'TypeError' in text:
        problems.append(text)


qInstallMessageHandler(collect)


class Launches(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    @Slot(str)
    def launch(self, game_id):
        self.calls.append(game_id)


def load():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    bridge = Launches()
    engine.rootContext().setContextProperty('bridge', bridge)
    engine.rootContext().setContextProperty('initialGames', FIXTURE.read_text())
    engine.rootContext().setContextProperty('initialService', 'ready')
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    if not roots:
        raise SystemExit('Main.qml did not load')
    return app, engine, roots[0], bridge


def plain(value):
    """QML hands back QJSValue for JS objects; convert to plain Python."""
    if hasattr(value, 'toVariant'):
        return value.toVariant()
    return value


def check(condition, message):
    if not condition:
        problems.append(message)
        print('FAIL:', message, file=sys.stderr)


def main():
    app, engine, window, bridge = load()
    window.show()
    QTest.qWait(200)

    games = json.loads(FIXTURE.read_text())['games']
    valid = [g for g in games if g.get('valid')]
    check(window.property('visibleCount') == len(valid),
          f"expected {len(valid)} titles, got {window.property('visibleCount')}")
    check(window.property('schemaVersion') == 1, 'schema must be 1')

    window.setProperty('filter', 'racer')
    check(window.property('visibleCount') == 1, 'search "racer" should match one title')
    window.setProperty('filter', '')
    check(window.property('visibleCount') == len(valid), 'clearing the search restores every title')

    # A blocked title is shown with its reason, and it cannot be launched from the detail panel.
    window.setProperty('selectedId', 'valorant')
    QTest.qWait(120)
    selected = plain(window.property('selectedGame'))
    check(selected is not None and selected['launchable'] is False, 'valorant must be blocked')
    window.setProperty('selectedId', 'racer')
    QTest.qWait(120)
    selected = plain(window.property('selectedGame'))
    check(selected is not None and selected['name'] == 'Circuit Racer', 'racer must be selectable')
    window.setProperty('selectedId', 'racer')
    window.launch('racer')
    check(bridge.calls == ['racer'], f'launch should reach the bridge once, got {bridge.calls}')
    window.launch('valorant')
    check(bridge.calls == ['racer'], 'a blocked title must not reach the bridge from the QML')

    PREVIEWS.mkdir(parents=True, exist_ok=True)
    window.setProperty('selectedId', 'racer')
    QTest.qWait(250)
    QQuickWindow.grabWindow(window).save(str(PREVIEWS / 'game-library.png'))
    window.setProperty('selectedId', 'valorant')
    QTest.qWait(250)
    QQuickWindow.grabWindow(window).save(str(PREVIEWS / 'game-library-blocked.png'))

    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    print('game library UI checks OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
