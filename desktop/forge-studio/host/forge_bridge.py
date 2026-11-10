"""Forge Studio backend logic: the only way the Studio UI reaches the Forge toolchain.

The QML never builds command lines. It asks for one of the fixed operations below,
and this module maps it to an `ominx-forge` argument vector. Arguments go to the
program as a list, never through a shell. Paths are checked before they reach the
CLI, and the CLI repeats every check (it owns the real confinement rules).

The C++ host (host/forge_bridge.cpp) implements the same table. Keep them in step;
tests/test_forge_studio.py checks both against the CLI.
"""
import json
import os
import subprocess
from pathlib import Path

# Operation name -> (argv template, needs a relative path, needs stdin content).
OPERATIONS = {
    'tree': (['tree', '{dir}', '--json'], False, False),
    'check': (['check', '{dir}', '--json'], False, False),
    'run': (['run', '{dir}'], False, False),
    'test': (['test', '{dir}'], False, False),
    'build': (['build', '{dir}'], False, False),
    'read': (['read', '{dir}', '{rel}'], True, False),
    'write': (['write', '{dir}', '{rel}'], True, True),
}

# Relative paths the Studio may open or save. The CLI enforces the same set.
EDITABLE_TOP = ('src/', 'assets/')
EDITABLE_FILES = ('forge.project',)
MAX_TEXT = 1024 * 1024


class BridgeError(Exception):
    """A request the Studio refuses before running anything."""


def check_project_dir(path):
    if not isinstance(path, str) or not path or '\n' in path or '\0' in path:
        raise BridgeError('project folder is not valid')
    if not os.path.isabs(path):
        raise BridgeError('project folder must be an absolute path')
    if not os.path.isdir(path):
        raise BridgeError('project folder does not exist')
    return path


def check_rel(rel):
    if not isinstance(rel, str) or not rel:
        raise BridgeError('no file was chosen')
    if rel.startswith('-') or '\n' in rel or '\0' in rel or '\\' in rel:
        raise BridgeError('that file name is not allowed')
    if rel in EDITABLE_FILES:
        return rel
    if rel.startswith(EDITABLE_TOP) and not rel.split('/', 1)[1].startswith('.') and '..' not in rel.split('/'):
        return rel
    raise BridgeError('only files in src/, assets/ and forge.project can be used in Studio')


def check_new_project(folder, ident, name):
    """New projects: the folder must not exist yet and its parent must. The CLI checks the id."""
    if not isinstance(folder, str) or not os.path.isabs(folder) or '\n' in folder or '\0' in folder:
        raise BridgeError('new project folder must be an absolute path')
    if os.path.lexists(folder):
        raise BridgeError('that folder already exists')
    if not os.path.isdir(os.path.dirname(folder)):
        raise BridgeError('the parent folder does not exist')
    for label, value in (('app ID', ident), ('name', name)):
        if not isinstance(value, str) or not value.strip() or value.startswith('-') or '\n' in value or '\0' in value:
            raise BridgeError('the %s is not valid' % label)
    return folder


def build_argv(binary, op, project_dir, rel=None, content=None):
    """Return the argv for one operation. Raises BridgeError for anything unknown."""
    if op == 'new':
        folder = check_new_project(project_dir, rel, content)
        return [binary, 'new', folder, '--id', rel.strip(), '--name', content.strip()]
    if op not in OPERATIONS:
        raise BridgeError('unknown operation')
    template, needs_rel, _ = OPERATIONS[op]
    check_project_dir(project_dir)
    values = {'dir': project_dir}
    if needs_rel:
        values['rel'] = check_rel(rel)
    return [binary] + [part.format(**values) for part in template]


def run_operation(binary, op, project_dir, rel=None, content=None, timeout=120):
    """Run one operation and return a result dict the QML can display."""
    argv = build_argv(binary, op, project_dir, rel, content)
    needs_stdin = op == 'write'
    data = None
    if needs_stdin:
        if not isinstance(content, str):
            raise BridgeError('nothing to save')
        data = content.encode('utf-8', 'surrogateescape')
        if len(data) > MAX_TEXT:
            raise BridgeError('file is too large for Studio (1 MiB limit)')
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'LC_ALL', 'OMINX_FORGE_OS_RELEASE')}
    proc = subprocess.run(argv, input=data, capture_output=True, timeout=timeout, env=env)
    result = {
        'op': op,
        'ok': proc.returncode == 0,
        'exit': proc.returncode,
        'stdout': proc.stdout.decode('utf-8', 'replace'),
        'stderr': proc.stderr.decode('utf-8', 'replace'),
    }
    if op in ('tree', 'check'):
        # check exits 1 with a JSON document on stdout when the program has errors.
        try:
            result['data'] = json.loads(result['stdout'])
        except ValueError:
            result['data'] = [] if op == 'tree' else {'ok': False, 'diagnostics': []}
    return result


def read_project_text(binary, project_dir, rel):
    """Helper for tests and the dev host: read one editable file as text."""
    result = run_operation(binary, 'read', project_dir, rel)
    if not result['ok']:
        raise BridgeError(result['stderr'].strip() or 'cannot read file')
    return result['stdout']


def platform_is_ominx(os_release='/etc/os-release'):
    """Studio's own gate, same rule as the CLI: the system must identify as ominx."""
    try:
        text = Path(os.environ.get('OMINX_FORGE_OS_RELEASE', os_release)
                    if os.environ.get('OMINX_STUDIO_DEV') == '1' else os_release).read_text()
    except OSError:
        return False
    for line in text.splitlines():
        if line.strip() == 'ID=ominx':
            return True
    return False
