#!/usr/bin/env python3
"""Development host for the OminX Game Library QML.

It supplies the two inputs the QML expects: the schema-1 JSON from
`ominx-win game list --json` (or a fixture file) and a `bridge` object whose
launch(id) runs `ominx-win game launch <id>`. It is a dev harness only. On the
target, the same QML is driven by a native bridge with the same two inputs.

usage: gamelib.py [--fixture PATH] [--service ready|preparing|stopped]"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

HERE = Path(__file__).resolve().parent
QML = HERE.parent / 'qml/Main.qml'
DEFAULT_FIXTURE = HERE.parent / 'fixtures/games.json'


class Bridge(QObject):
    """Launches through the same CLI the user would run. The daemon repeats the gate."""

    def __init__(self, win):
        super().__init__()
        self.win = win

    @Slot(str)
    def launch(self, game_id):
        if not game_id.replace('-', '').isalnum():
            return
        subprocess.Popen([self.win, 'game', 'launch', game_id])


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', default=str(DEFAULT_FIXTURE))
    parser.add_argument('--service', default='ready', choices=['ready', 'preparing', 'stopped'])
    args = parser.parse_args(argv)

    win = os.environ.get('OMINX_WIN_BINARY') or shutil.which('ominx-win') or 'ominx-win'
    games_json = Path(args.fixture).read_text()

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    bridge = Bridge(win)
    engine.rootContext().setContextProperty('bridge', bridge)
    engine.rootContext().setContextProperty('initialGames', games_json)
    engine.rootContext().setContextProperty('initialService', args.service)
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
