"""Forge Studio: bridge rules, the bridge against the real CLI, the contract shared by
the QML, the Python dev host and the C++ host, and QML lint.

The bridge is tested without a display. The QML is linted with pyside6-qmllint when
it is available (OMINX_QMLLINT, or the PySide6 install next to OMINX_UI_PYTHON). The
C++ host is checked for contract consistency only, because no Qt C++ headers are
available in every build sandbox."""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / 'desktop/forge-studio'
HOST = STUDIO / 'host'
QML_DIR = STUDIO / 'qml'
BIN = os.environ.get('OMINX_FORGE_BINARY', str(ROOT / 'build/host/ominx-forge-test'))

sys.path.insert(0, str(HOST))
import forge_bridge  # noqa: E402


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def qmllint_path():
    candidates = [os.environ.get('OMINX_QMLLINT'), shutil.which('pyside6-qmllint')]
    ui_python = os.environ.get('OMINX_UI_PYTHON')
    if ui_python:
        candidates.insert(1, str(Path(ui_python).with_name('pyside6-qmllint')))
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


class BridgeRules(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / 'proj'
        (self.dir / 'src').mkdir(parents=True)
        (self.dir / 'assets').mkdir()
        (self.dir / 'forge.project').write_text('format=1\n')

    def tearDown(self):
        self._tmp.cleanup()

    def assertRefused(self, fn, *args):
        with self.assertRaises(forge_bridge.BridgeError):
            fn(*args)

    def test_fixed_argument_vectors(self):
        d = str(self.dir)
        self.assertEqual(forge_bridge.build_argv('/bin/ominx-forge', 'tree', d),
                         ['/bin/ominx-forge', 'tree', d, '--json'])
        self.assertEqual(forge_bridge.build_argv('/bin/ominx-forge', 'check', d),
                         ['/bin/ominx-forge', 'check', d, '--json'])
        self.assertEqual(forge_bridge.build_argv('/bin/ominx-forge', 'run', d),
                         ['/bin/ominx-forge', 'run', d])
        self.assertEqual(forge_bridge.build_argv('/bin/ominx-forge', 'read', d, 'src/main.fg'),
                         ['/bin/ominx-forge', 'read', d, 'src/main.fg'])
        self.assertEqual(forge_bridge.build_argv('/bin/ominx-forge', 'write', d, 'assets/a.txt'),
                         ['/bin/ominx-forge', 'write', d, 'assets/a.txt'])

    def test_unknown_operations_are_refused(self):
        self.assertRefused(forge_bridge.build_argv, 'x', 'exec', str(self.dir))
        self.assertRefused(forge_bridge.build_argv, 'x', 'sh -c id', str(self.dir))

    def test_project_folder_rules(self):
        self.assertRefused(forge_bridge.check_project_dir, 'relative/path')
        self.assertRefused(forge_bridge.check_project_dir, str(self.dir) + '\nX')
        self.assertRefused(forge_bridge.check_project_dir, str(self.dir) + '/missing')
        self.assertRefused(forge_bridge.check_project_dir, '')

    def test_file_rules(self):
        for bad in ('', '-rf', '../x.fg', 'src/../x.fg', 'src/.secret.fg', 'build/x', 'stray.txt',
                    '/etc/passwd', 'src\\x.fg', 'src/a\nb.fg', 'src/a\x00b.fg'):
            self.assertRefused(forge_bridge.check_rel, bad)
        for good in ('forge.project', 'src/main.fg', 'src/lib/util.fg', 'assets/icons/a.txt'):
            self.assertEqual(forge_bridge.check_rel(good), good)

    def test_new_project_rules(self):
        new = str(Path(self._tmp.name) / 'fresh')
        self.assertEqual(forge_bridge.build_argv('/bin/ominx-forge', 'new', new, 'org.example.a', 'Name'),
                         ['/bin/ominx-forge', 'new', new, '--id', 'org.example.a', '--name', 'Name'])
        self.assertRefused(forge_bridge.build_argv, '/bin/ominx-forge', 'new', str(self.dir), 'org.example.a', 'N')
        self.assertRefused(forge_bridge.build_argv, '/bin/ominx-forge', 'new',
                           str(Path(self._tmp.name) / 'no/such/parent'), 'org.example.a', 'N')
        self.assertRefused(forge_bridge.build_argv, '/bin/ominx-forge', 'new', new, '-x', 'N')
        self.assertRefused(forge_bridge.build_argv, '/bin/ominx-forge', 'new', new, 'org.example.a', '  ')

    def test_write_needs_content_and_a_size_limit(self):
        self.assertRefused(forge_bridge.run_operation, BIN, 'write', str(self.dir), 'src/main.fg', None)
        big = 'x' * (1024 * 1024 + 1)
        self.assertRefused(forge_bridge.run_operation, BIN, 'write', str(self.dir), 'src/main.fg', big)


class BridgeAgainstTheCli(unittest.TestCase):
    """The bridge drives the real ominx-forge test build (the same binary Studio ships with)."""

    def setUp(self):
        if not Path(BIN).exists():
            self.skipTest('build/host/ominx-forge-test not built')
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        self.os_release = self.work / 'os-release'
        self.os_release.write_text('ID=ominx\n')
        os.environ['OMINX_FORGE_OS_RELEASE'] = str(self.os_release)
        self.proj = self.work / 'Puzzle'

    def tearDown(self):
        os.environ.pop('OMINX_FORGE_OS_RELEASE', None)
        self._tmp.cleanup()

    def run_op(self, op, rel=None, content=None):
        return forge_bridge.run_operation(BIN, op, str(self.proj), rel, content)

    def test_full_project_cycle(self):
        r = forge_bridge.run_operation(BIN, 'new', str(self.proj), 'org.example.puzzle', 'Puzzle')
        self.assertTrue(r['ok'], r['stderr'])
        self.assertTrue((self.proj / 'src/main.fg').is_file())

        tree = self.run_op('tree')
        self.assertTrue(tree['ok'])
        paths = [e['path'] for e in tree['data']]
        self.assertIn('src/main.fg', paths)
        self.assertIn('forge.project', paths)

        self.assertTrue(self.run_op('check')['ok'])
        self.assertIn('Hello, OminX!', self.run_op('run')['stdout'])
        self.assertIn('1 passed, 0 failed', self.run_op('test')['stdout'])

        saved = self.run_op('write', 'src/main.fg', 'fn main() { print("edited") }\n')
        self.assertTrue(saved['ok'], saved['stderr'])
        self.assertEqual(self.run_op('read', 'src/main.fg')['stdout'], 'fn main() { print("edited") }\n')
        self.assertIn('edited', self.run_op('run')['stdout'])

        built = self.run_op('build')
        self.assertTrue(built['ok'], built['stderr'])
        self.assertTrue(any((self.proj / 'build').glob('*.opkgx')))

    def test_check_returns_structured_diagnostics(self):
        forge_bridge.run_operation(BIN, 'new', str(self.proj), 'org.example.puzzle', 'Puzzle')
        self.run_op('write', 'src/main.fg', 'fn main() { print(nope) }\n')
        r = self.run_op('check')
        self.assertFalse(r['ok'])
        self.assertEqual(r['data']['diagnostics'][0]['file'], 'src/main.fg')
        self.assertEqual(r['data']['diagnostics'][0]['message'], "undefined name 'nope'")

    def test_no_shell_is_involved(self):
        # A name full of shell syntax is passed to the CLI as one argument, never executed.
        marker = self.work / 'pwned'
        name = '$(touch %s)' % marker
        r = forge_bridge.run_operation(BIN, 'new', str(self.proj), 'org.example.shell', name)
        self.assertFalse(marker.exists())
        self.assertEqual(r['exit'] in (0, 1), True, r['stderr'])

    def test_platform_is_checked_by_the_cli_too(self):
        # Studio's own gate can be bypassed in development; the CLI still refuses off OminXOS.
        self.assertEqual(forge_bridge.run_operation(BIN, 'new', str(self.proj), 'org.example.puzzle', 'Puzzle')['ok'], True)
        other = self.work / 'other-release'
        other.write_text('ID=ubuntu\n')
        env = dict(os.environ, OMINX_FORGE_OS_RELEASE=str(other))
        r = subprocess.run([BIN, 'check', str(self.proj)], capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(r.returncode, 3)
        self.assertIn('Forge runs only on OminXOS', r.stderr)


class PlatformGate(unittest.TestCase):
    def test_studio_gate_reads_the_system_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            ominx = Path(tmp) / 'ominx'
            ominx.write_text('NAME=OminX\nID=ominx\n')
            other = Path(tmp) / 'other'
            other.write_text('ID=ubuntu\nID_LIKE=ominx-not\n')
            old = dict(os.environ)
            try:
                os.environ.pop('OMINX_STUDIO_DEV', None)
                os.environ.pop('OMINX_FORGE_OS_RELEASE', None)
                self.assertTrue(forge_bridge.platform_is_ominx(str(ominx)))
                self.assertFalse(forge_bridge.platform_is_ominx(str(other)))
                self.assertFalse(forge_bridge.platform_is_ominx(str(Path(tmp) / 'absent')))
                # The fixture override needs the explicit dev switch.
                os.environ['OMINX_FORGE_OS_RELEASE'] = str(ominx)
                self.assertFalse(forge_bridge.platform_is_ominx(str(other)))
                os.environ['OMINX_STUDIO_DEV'] = '1'
                self.assertTrue(forge_bridge.platform_is_ominx(str(other)))
            finally:
                os.environ.clear()
                os.environ.update(old)


class ContractConsistency(unittest.TestCase):
    """QML, the Python host and the C++ host must agree on one contract."""

    def setUp(self):
        self.qml = {p.name: p.read_text() for p in QML_DIR.glob('*.qml')}
        self.py_host = (HOST / 'forge_studio_dev.py').read_text()
        self.cpp = (HOST / 'forge_bridge.cpp').read_text()
        self.cpp_h = (HOST / 'forge_bridge.h').read_text()

    def test_operations_match_across_hosts(self):
        py_ops = set(forge_bridge.OPERATIONS) | {'new'}
        cpp_ops = set(re.findall(r'op == QLatin1String\("([a-z]+)"\)', self.cpp))
        cpp_ops |= set(re.findall(r'op == QLatin1String\("([a-z]+)"\) \|\|', self.cpp))
        cpp_ops |= set(re.findall(r'\|\| op == QLatin1String\("([a-z]+)"\)', self.cpp))
        self.assertEqual(py_ops, cpp_ops)

    def test_finished_signal_arity_matches(self):
        py_sig = re.search(r'finished = Signal\(([^)]*)\)', self.py_host).group(1)
        self.assertEqual(len(py_sig.split(',')), 7)
        cpp_sig = re.search(r'void finished\((.*?)\);', self.cpp_h, re.S).group(1)
        self.assertEqual(cpp_sig.count(','), 6)
        emitted = re.findall(r'emit finished\(', self.cpp)
        self.assertEqual(len(emitted), 2)  # refusals and finished processes

    def test_qml_uses_the_contract(self):
        main = self.qml['Main.qml']
        self.assertIn('forge.request(String(requestSeq), op, dir, rel || "", content || "")', main)
        self.assertIn('function onFinished(requestId, op, ok, exitCode, stdout, stderr, dataJson)', main)

    def test_python_and_native_hosts_use_the_same_binary_path(self):
        self.assertIn('/bin/ominx-forge', self.cpp_h)
        self.assertIn("'/bin/ominx-forge'", self.py_host)

    def test_qml_never_builds_commands(self):
        for name, text in self.qml.items():
            self.assertNotIn('Process', text, name)
            self.assertNotIn('Qt.openUrlExternally', text, name)
            self.assertNotIn('XMLHttpRequest', text, name)


class Presentation(unittest.TestCase):
    def test_cmake_project_lists_every_qml_file(self):
        cmake = STUDIO / 'CMakeLists.txt'
        self.assertTrue(cmake.exists(), 'build-forge-studio.sh configures desktop/forge-studio')
        text = cmake.read_text()
        for qml in sorted(QML_DIR.glob('*.qml')):
            self.assertIn('qml/' + qml.name, text, qml.name + ' missing from QML_FILES')
        self.assertIn('QT_QML_SINGLETON_TYPE', text)
        for src in ('host/forge_studio.cpp', 'host/forge_bridge.cpp'):
            self.assertIn(src, text)
            self.assertTrue((STUDIO / src).exists())

    def test_qml_files_present(self):
        for name in ('Main.qml', 'Navigator.qml', 'Editor.qml', 'OutputPanel.qml', 'NewProjectDialog.qml',
                     'Theme.qml', 'qmldir'):
            self.assertTrue((QML_DIR / name).is_file(), name)

    def test_brand_palette_is_used(self):
        theme = (QML_DIR / 'Theme.qml').read_text().lower()
        for colour in ('#101d32', '#74e0c7', '#123d46', '#244767', '#eff9f7'):
            self.assertIn(colour, theme)

    def test_no_raster_assets_or_network_in_the_ui(self):
        for path in list(QML_DIR.glob('*.qml')) + [HOST / 'forge_studio.cpp', HOST / 'forge_bridge.cpp']:
            text = path.read_text()
            self.assertNotIn('localhost', text, path.name)
            self.assertNotIn('127.0.0.1', text, path.name)
            self.assertNotRegex(text, r'https?://', path.name)
            self.assertNotRegex(text, r'\.(png|jpe?g|webp|gif)\b', path.name)

    def test_desktop_entry_and_mime_type_are_packaged(self):
        mk = load_module('mk', ROOT / 'scripts/make-initramfs.py')
        import configparser
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(mk.FORGE_STUDIO_DESKTOP_ENTRY.decode())
        entry = parser['Desktop Entry']
        self.assertEqual(entry['Exec'], '/bin/forge-studio %f')
        self.assertEqual(entry['MimeType'], 'application/x-forge;')
        self.assertIn('application/x-forge', mk.FORGE_MIME_XML.decode())
        self.assertIn('*.fg', mk.FORGE_MIME_XML.decode())
        self.assertIn('ominx-forge', mk.WIN_BINARIES)

    def test_python_hosts_parse(self):
        import ast
        for name in ('forge_studio_dev.py', 'forge_bridge.py'):
            ast.parse((HOST / name).read_text(), filename=name)


class DevHostBridge(unittest.TestCase):
    """The Python host's signal path, without a window. Needs PySide6 (OMINX_UI_PYTHON)."""

    def setUp(self):
        try:
            import forge_studio_dev
        except ImportError:
            self.skipTest('PySide6 not importable here (run with OMINX_UI_PYTHON)')
        if not Path(BIN).exists():
            self.skipTest('build/host/ominx-forge-test not built')
        self.dev = forge_studio_dev
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        self.os_release = self.work / 'os-release'
        self.os_release.write_text('ID=ominx\n')
        self.old_env = dict(os.environ)
        os.environ['OMINX_FORGE_OS_RELEASE'] = str(self.os_release)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self._tmp.cleanup()

    def test_finished_signal_carries_the_result(self):
        proj = self.work / 'Dev'
        bridge = self.dev.Bridge(BIN)
        seen = []
        bridge.finished.connect(lambda *args: seen.append(args))
        bridge._run('7', 'new', str(proj), 'org.example.dev', 'Dev')
        self.assertEqual(seen[-1][:4], ('7', 'new', True, 0))
        bridge._run('8', 'tree', str(proj), '', '')
        rid, op, ok, code, out, err, data = seen[-1]
        self.assertEqual((rid, op, ok, code), ('8', 'tree', True, 0), err)
        self.assertIn('src/main.fg', data)
        bridge._run('9', 'read', str(proj), 'src/nope.fg', '')
        self.assertFalse(seen[-1][2])
        bridge._run('10', 'exec', str(proj), '', '')
        self.assertEqual(seen[-1][3], -1)
        self.assertIn('unknown operation', seen[-1][5])


class Qml(unittest.TestCase):
    def test_qml_lints_clean(self):
        lint = qmllint_path()
        if lint is None:
            self.skipTest('pyside6-qmllint not found (set OMINX_QMLLINT or OMINX_UI_PYTHON)')
        files = sorted(p.name for p in QML_DIR.glob('*.qml'))
        r = subprocess.run([lint, '-I', str(QML_DIR), *files], cwd=QML_DIR,
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('Warning', r.stdout + r.stderr)


class QmlLoads(unittest.TestCase):
    """Loads Main.qml with the dev bridge, headless, in a subprocess (needs OMINX_UI_PYTHON)."""

    SCRIPT = """
import sys, os
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
sys.path.insert(0, sys.argv[1])
import forge_studio_dev as d
app = QGuiApplication(sys.argv)
eng = QQmlApplicationEngine()
msgs = []
eng.warnings.connect(lambda ws: msgs.extend(w.toString() for w in ws))
eng.rootContext().setContextProperty('forge', d.Bridge(sys.argv[2]))
eng.load(QUrl.fromLocalFile(sys.argv[3]))
print('roots', len(eng.rootObjects()))
print('warnings', len(msgs))
for m in msgs: print('W', m)
QTimer.singleShot(300, app.quit)
app.exec()
"""

    def test_main_qml_loads_without_warnings(self):
        ui_python = os.environ.get('OMINX_UI_PYTHON')
        if not ui_python or not Path(ui_python).exists():
            self.skipTest('set OMINX_UI_PYTHON to a Python with PySide6')
        if not Path(BIN).exists():
            self.skipTest('build/host/ominx-forge-test not built')
        env = dict(os.environ, OMINX_STUDIO_DEV='1', OMINX_FORGE_BINARY=BIN,
                   QT_QPA_PLATFORM='offscreen')
        r = subprocess.run([ui_python, '-c', self.SCRIPT, str(STUDIO / 'host'), BIN,
                            str(QML_DIR / 'Main.qml')], env=env, capture_output=True,
                           text=True, timeout=120)
        if r.returncode != 0 and ('ImportError' in r.stderr or 'cannot open shared object' in r.stderr):
            self.skipTest('Qt runtime not loadable here: ' + r.stderr.strip()[-200:])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('roots 1', r.stdout)
        self.assertIn('warnings 0', r.stdout, r.stdout)


if __name__ == '__main__':
    unittest.main()
