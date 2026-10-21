#!/usr/bin/env python3
"""Package only source-built runtime libraries/data; exclude headers and host tools."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SYS = ROOT / 'build/graphics-sysroot'
DEST = ROOT / 'build/graphics-runtime'
COMPILER = ROOT / 'build/toolchain/bin/x86_64-linux-musl-gcc'
if DEST.is_symlink():
    raise SystemExit('Refusing runtime destination symlink')
if DEST.exists():
    shutil.rmtree(DEST)
DEST.mkdir(mode=0o755)


def copy(source, name):
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        if not source.resolve().is_relative_to(SYS.resolve()):
            raise ValueError('Source SDK link escapes sysroot')
        target.symlink_to(source.readlink())
    else:
        shutil.copyfile(source, target)
        target.chmod(0o755 if source.read_bytes()[:4] == b'\x7fELF' else 0o644)


for source in sorted((SYS/'usr/lib').rglob('*')):
    if source.is_dir() or not ('.so' in source.name):
        continue
    copy(source, source.relative_to(SYS))
for directory in ('usr/share/X11/xkb', 'usr/share/drirc.d'):
    source = SYS / directory
    if source.exists():
        for path in sorted(source.rglob('*')):
            if path.is_file() or path.is_symlink():
                copy(path, path.relative_to(SYS))
# Compiler runtime paths must resolve inside our source toolchain, never the host.
for library in ('libc.so', 'libstdc++.so.6', 'libgcc_s.so.1'):
    path = Path(subprocess.check_output([str(COMPILER), '-print-file-name='+library], text=True).strip()).resolve()
    if not path.is_file() or not path.is_relative_to(ROOT/'build/toolchain'):
        raise ValueError('Missing source compiler runtime: '+library)
    dest = DEST / 'lib' / library
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(path, dest)
    dest.chmod(0o755)
(DEST/'lib/ld-musl-x86_64.so.1').symlink_to('libc.so')
copy(ROOT/'build/ominx-render-probe', 'usr/bin/ominx-render-probe')
# Preserve component license notices and corresponding downloaded source archives.
licenses = DEST/'usr/share/licenses/ominx-graphics'
licenses.mkdir(parents=True)
notices = {
 'graphics-libffi':['LICENSE'], 'graphics-wayland':['COPYING'],
 'graphics-wayland-protocols':['COPYING'], 'graphics-xkbcommon':['LICENSE'],
 'graphics-xkeyboard-config':['COPYING'], 'graphics-zlib':['LICENSE'],
 'graphics-libdrm':['data/meson.build'], 'graphics-mesa':['docs/license.rst'],
 'expat':['expat/COPYING'],
}
for package, names in notices.items():
    base = ROOT/'build/sources'/package
    files = [base/name for name in names]
    if (base/'licenses').is_dir():
        files += sorted(p for p in (base/'licenses').rglob('*') if p.is_file())
    (licenses/package).write_bytes(b''.join(b'===== '+p.relative_to(base).as_posix().encode()+b' =====\n'+p.read_bytes()+b'\n' for p in files))
# GCC runtime exception and musl copyright come from the exact toolchain sources.
# Cached compiler jobs need not retain extracted source trees; these notices
# are tracked with their upstream source identities.
for name in ('MUSL-COPYRIGHT', 'GCC-COPYING3', 'GCC-RUNTIME-EXCEPTION'):
    shutil.copyfile(ROOT/'desktop/graphics/licenses'/name, licenses/name)
for path in DEST.rglob('*'):
    if path.is_symlink():
        continue
    if path.is_dir():
        path.chmod(0o755)
    elif path.read_bytes()[:4] == b'\x7fELF':
        subprocess.run([str(COMPILER).replace('-gcc','-strip'), '--strip-unneeded', str(path)], check=True)
    else:
        path.chmod(0o644)
spec = importlib.util.spec_from_file_location('runtime_elf', ROOT/'scripts/runtime-elf.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
nodes, binaries = m.audit(DEST)
report = {name: dict(mode=oct(mode), sha256=hashlib.sha256(data).hexdigest(), elf=binaries.get(name))
          for name, (mode,data) in nodes.items()}
(ROOT/'build/provenance/graphics-runtime.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'Audited {len(binaries)} source-linked ELF objects and {len(nodes)} runtime entries')

archives=ROOT/'build/graphics-sources'
archives.mkdir(exist_ok=True)
for name, source in json.load(open(ROOT/'desktop/graphics/sources.json')).items():
    archive=ROOT/'build/downloads'/(source['sha256']+'.tar')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=source['sha256']:
        raise ValueError('Source archive changed after build')
    shutil.copyfile(archive,archives/(name+'-'+source['version']+'.tar'))
for source in ('graphics-xkbcommon','expat'):
    subprocess.run(['git','-C',str(ROOT/'build/sources'/source),'archive','--format=tar.gz',
                    '--output='+str(archives/(source+'.tar.gz')),'HEAD'],check=True)
sdk={}
for p in sorted(SYS.rglob('*')):
    if p.is_symlink():
        sdk[p.relative_to(SYS).as_posix()]={'link':p.readlink().as_posix()}
    elif p.is_file():
        sdk[p.relative_to(SYS).as_posix()]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(ROOT/'build/provenance/graphics-sdk.json').write_text(json.dumps(sdk,indent=2)+'\n')
