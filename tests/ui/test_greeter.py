#!/usr/bin/env python3
"""Qt 6 rendering/interaction tests. Mock authentication is NOT PAM/login validation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
from pathlib import Path
import sys
from PySide6.QtCore import QObject, Property, Signal, Slot, QAbstractListModel, QModelIndex, Qt, QUrl, QMetaObject, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/greeter'
OUT.mkdir(parents=True, exist_ok=True)
errors = []
def message(kind, context, text):
    print(text, file=sys.stderr)
    if any(word in text for word in ('ReferenceError', 'TypeError', 'is not a type', 'Cannot assign', 'Unable to assign')):
        errors.append(text)
qInstallMessageHandler(message)

class Users(QObject):
    @Property(str, constant=True)
    def lastUser(self): return 'Alex'

class Keyboard(QObject):
    @Property(bool, constant=True)
    def capsLock(self): return False

class Sessions(QAbstractListModel):
    @Property(int, constant=True)
    def lastIndex(self): return 0
    def rowCount(self, parent=QModelIndex()): return 2
    def roleNames(self): return {Qt.UserRole + 1: b'name'}
    def data(self, index, role=Qt.DisplayRole):
        return ['Plasma (Wayland)', 'Plasma (X11)'][index.row()] if role == Qt.UserRole + 1 else None

class Sddm(QObject):
    loginFailed = Signal()
    loginSucceeded = Signal()
    def __init__(self):
        super().__init__(); self.calls = []; self.off = 0; self.restarts = 0
    @Property(bool, constant=True)
    def canPowerOff(self): return True
    @Property(bool, constant=True)
    def canReboot(self): return True
    @Slot(str, str, int)
    def login(self, user, password, session): self.calls.append((user, password, session))
    @Slot()
    def powerOff(self): self.off += 1
    @Slot()
    def reboot(self): self.restarts += 1

app = QGuiApplication(sys.argv)
view = QQuickView()
view.setResizeMode(QQuickView.SizeRootObjectToView)
users, keyboard, sessions, sddm = Users(), Keyboard(), Sessions(), Sddm()
for name, value in [('userModel', users), ('keyboard', keyboard), ('sessionModel', sessions), ('sddm', sddm)]:
    view.rootContext().setContextProperty(name, value)
view.setSource(QUrl.fromLocalFile(str(ROOT / 'desktop/sddm/ominx/Main.qml')))
if view.status() == QQuickView.Error:
    raise RuntimeError([error.toString() for error in view.errors()])
view.resize(1440, 900)
view.show()
QTest.qWait(300)
root = view.rootObject()
def child(name):
    result = root.findChild(QObject, name)
    assert result is not None, name
    return result

def call(obj, method):
    assert QMetaObject.invokeMethod(obj, method), method
    QTest.qWait(30)

assert child('password').property('echoMode') == 2  # TextInput.Password
assert child('username').property('text') == 'Alex'
assert view.grabWindow().save(str(OUT / 'ominx-login-1440.png'))
username, password = child('username'), child('password')
username.setProperty('text', '')
call(root, 'login')
assert not sddm.calls and 'username' in root.property('failure')
username.setProperty('text', 'Alex')
password.setProperty('text', 'ui-test-not-a-real-password')
call(password, 'forceActiveFocus')
QTest.keyClick(view, Qt.Key_Return)
QTest.qWait(50)
assert len(sddm.calls) == 1 and sddm.calls[0] == ('Alex', 'ui-test-not-a-real-password', 0)
sddm.calls.clear()
assert root.property('busy')
assert not child('signIn').property('enabled')
call(root, 'login')
assert not sddm.calls  # duplicate submission blocked
sddm.loginFailed.emit()
QTest.qWait(50)
assert not root.property('busy') and password.property('text') == ''
assert 'Sign-in failed' in root.property('failure')
assert view.grabWindow().save(str(OUT / 'ominx-login-error.png'))
# No session means no credential submission.
child('session').setProperty('currentIndex', -1)
call(root, 'login')
assert not sddm.calls and 'No desktop session' in root.property('failure')
child('session').setProperty('currentIndex', 0)
root.setProperty('failure', '')
call(child('shutdownButton'), 'clicked')
assert sddm.off == 0
call(child('powerConfirmation'), 'reject')
assert sddm.off == 0
call(child('restartButton'), 'clicked')
assert sddm.restarts == 0
call(child('powerConfirmation'), 'accept')
assert sddm.restarts == 1
for width, height in [(1024, 768), (800, 600)]:
    view.resize(width, height); QTest.qWait(150)
    panel = child('loginPanel')
    assert panel.property('x') >= 0 and panel.property('y') >= 60
    assert panel.property('y') + panel.property('height') <= height - 45
    assert view.grabWindow().save(str(OUT / f'ominx-login-{width}.png'))
assert not errors, errors
print('PASS Qt 6 theme: render 1440/1024/800, masked password, keyboard submit, busy/error/reset, session guard, confirmed power callbacks')
