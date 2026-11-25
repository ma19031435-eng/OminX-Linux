#!/usr/bin/env python3
"""Development host for Forge Studio. It runs the same QML as the native host.

It exposes the `forge` object that qml/Main.qml talks to:
  request(requestId, op, projectDir, rel, content)   -- asynchronous
  finished(requestId, op, ok, exitCode, stdout, stderr, dataJson)  -- signal

Every operation goes through forge_bridge.run_operation, which only builds the
fixed `ominx-forge` argument vectors. The native host (forge_studio.cpp) mirrors it.

usage: forge_studio_dev.py [--binary PATH]
  OMINX_FORGE_BINARY selects the ominx-forge build (the test build for development).
  OMINX_STUDIO_DEV=1 lets OMINX_FORGE_OS_RELEASE stand in for /etc/os-release.
"""
import argparse
import json
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import forge_bridge  # noqa: E402

QML = HERE.parent / 'qml/Main.qml'


class Bridge(QObject):
    finished = Signal(str, str, bool, int, str, str, str)

    def __init__(self, binary):
        super().__init__()
        self.binary = binary

    @Slot(str, str, str, str, str)
    def request(self, request_id, op, project_dir, rel, content):
        threading.Thread(target=self._run, args=(request_id, op, project_dir, rel, content),
                         daemon=True).start()

    def _run(self, request_id, op, project_dir, rel, content):
        try:
            result = forge_bridge.run_operation(self.binary, op, project_dir, rel or None, content)
        except forge_bridge.BridgeError as err:
            result = {'op': op, 'ok': False, 'exit': -1, 'stdout': '', 'stderr': str(err)}
        except (OSError, ValueError) as err:
            result = {'op': op, 'ok': False, 'exit': -1, 'stdout': '', 'stderr': 'Studio could not run Forge: %s' % err}
        data = json.dumps(result.get('data')) if 'data' in result else ''
        self.finished.emit(request_id, op, result['ok'], result['exit'], result['stdout'], result['stderr'], data)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', default=os.environ.get('OMINX_FORGE_BINARY', '/bin/ominx-forge'))
    args = parser.parse_args(argv)

    if not forge_bridge.platform_is_ominx():
        print('Forge Studio runs only on OminXOS.', file=sys.stderr)
        return 3

    app = QGuiApplication(sys.argv)
    app.setApplicationName('Forge Studio')
    engine = QQmlApplicationEngine()
    bridge = Bridge(args.binary)
    engine.rootContext().setContextProperty('forge', bridge)
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
