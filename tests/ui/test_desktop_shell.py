#!/usr/bin/env python3
"""Host Qt 6 checks for the original greeter host and desktop session QML.

Mock contexts only: this validates QML types, focus and wiring, not the real
authentication broker, seat or target Qt build.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
from pathlib import Path
import shutil
import sys
import tempfile
from PySide6.QtCore import (QAbstractListModel, QModelIndex, QObject, Property, QUrl, Qt,
                            QMetaObject, Signal, Slot, qInstallMessageHandler)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/desktop-shell-ui'
OUT.mkdir(parents=True, exist_ok=True)
errors = []


def message(kind, context, text):
    print(text, file=sys.stderr)
    if any(word in text for word in ('ReferenceError', 'TypeError', 'is not a type',
                                     'Cannot assign', 'Unable to assign', 'does not exist')):
        errors.append(text)


qInstallMessageHandler(message)


class Users(QObject):
    @Property(str, constant=True)
    def lastUser(self): return 'ominx'


class Keyboard(QObject):
    @Property(bool, constant=True)
    def capsLock(self): return False


class SessionList(QAbstractListModel):
    @Property(int, constant=True)
    def lastIndex(self): return 0

    def rowCount(self, parent=QModelIndex()): return 1

    def roleNames(self): return {Qt.DisplayRole: b'name'}

    def data(self, index, role=Qt.DisplayRole):
        return 'OminX Desktop' if role == Qt.DisplayRole else None


class Greeter(QObject):
    loginFailed = Signal()
    loginSucceeded = Signal()

    def __init__(self):
        super().__init__()
        self.power = 0
        self.logins = []

    @Property(bool, constant=True)
    def canPowerOff(self): return True

    @Property(bool, constant=True)
    def canReboot(self): return True

    @Slot(str, str, int)
    def login(self, user, password, session): self.logins.append((user, password, session))

    @Slot()
    def powerOff(self): self.power += 1

    @Slot()
    def reboot(self): self.power += 1


class Session(QObject):
    def __init__(self):
        super().__init__()
        self.logouts = 0
        self.power = 0

    @Property(str, constant=True)
    def userName(self): return 'ominx'

    @Property(list, constant=True)
    def facts(self): return ['User: ominx', 'Home: /home/ominx']

    @Slot()
    def logout(self): self.logouts += 1

    @Slot()
    def powerOff(self): self.power += 1

    @Slot()
    def reboot(self): self.power += 1


app = QGuiApplication(sys.argv)


alive = []


def load(source, properties):
    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    for name, value in properties.items():
        # QML holds an unowned pointer: Python must keep every context alive.
        alive.append(value)
        view.rootContext().setContextProperty(name, value)
    view.setSource(QUrl.fromLocalFile(str(source)))
    if view.status() == QQuickView.Error:
        raise RuntimeError([error.toString() for error in view.errors()])
    view.resize(1440, 900)
    view.show()
    QTest.qWait(400)
    return view


def child(root, name):
    result = root.findChild(QObject, name)
    assert result is not None, 'missing ' + name
    return result


temporary = tempfile.TemporaryDirectory()
shell = Path(temporary.name)
# The greeter host embeds the shared OminX theme exactly as the target build does.
shutil.copyfile(ROOT / 'desktop/desktop-shell/GreeterRoot.qml', shell / 'GreeterRoot.qml')
shutil.copyfile(ROOT / 'desktop/sddm/ominx/Main.qml', shell / 'Greeter.qml')

greeter = Greeter()
view = load(shell / 'GreeterRoot.qml',
            {'sddm': greeter, 'keyboard': Keyboard(), 'userModel': Users(), 'sessionModel': SessionList()})
root = view.rootObject()
assert root.property('passwordIsMasked'), 'password field is not masked'
assert child(root, 'username').property('text') == 'ominx', 'remembered username not prefilled'
assert view.grabWindow().save(str(OUT / 'greeter-1440.png')), 'greeter did not render'
QTest.keyClick(root, Qt.Key_End, Qt.ControlModifier | Qt.AltModifier)
QTest.qWait(120)
assert greeter.power == 1, 'keyboard power action did not reach the login context'
view.close()

session = Session()
view = load(ROOT / 'desktop/desktop-shell/Session.qml', {'session': session})
root = view.rootObject()
assert child(root, 'taskbar') is not None
assert child(root, 'startMenu').property('opened') is False
QTest.keyClick(root, Qt.Key_Esc)
QTest.qWait(200)
menu = child(root, 'startMenu')
assert menu.property('opened') is True, 'start menu did not open'
assert child(root, 'logoutButton').property('activeFocus') is True, 'logout is not the default action'
assert view.grabWindow().save(str(OUT / 'session-1440.png')), 'session did not render'
QTest.keyClick(root, Qt.Key_Return)
QTest.qWait(150)
assert session.logouts == 1, 'focused logout action did not run'
QTest.keyClick(root, Qt.Key_End, Qt.ControlModifier | Qt.AltModifier)
QTest.qWait(120)
assert session.power == 1, 'keyboard power action did not reach the session context'
QMetaObject.invokeMethod(child(root, 'informationButton'), 'clicked')
QTest.qWait(200)
assert child(root, 'sessionInformation').property('opened') is True, 'session information did not open'
view.close()
temporary.cleanup()
if errors:
    raise RuntimeError('QML errors: %r' % errors)
print('desktop shell QML: greeter host, keyboard power, start menu focus, logout and facts all wired')
