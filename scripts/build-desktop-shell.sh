#!/bin/sh
# Original desktop shell (greeter + session) against the source Qt Quick prefix.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
[ -f build/qt-prefix/lib/cmake/Qt6Quick/Qt6QuickConfig.cmake ] || {
    echo 'Build the source Qt Quick dependencies first (scripts/build-qt-quick-target.sh --dependencies-only)' >&2
    exit 1
}
cmake -S desktop/desktop-shell -B build/desktop-shell -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-musl.cmake" \
    -DCMAKE_PREFIX_PATH="$ROOT/build/qt-prefix" -DCMAKE_BUILD_TYPE=Release \
    -DQT_HOST_PATH="$ROOT/build/qt-quick-host" \
    -DQT_HOST_PATH_CMAKE_DIR="$ROOT/build/qt-quick-host/lib/cmake" \
    -DQT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH="$ROOT/build/qtshadertools-host;$ROOT/build/qtdeclarative-host-full"
cmake --build build/desktop-shell --parallel "${JOBS:-4}"
mkdir -p build/login
cp build/desktop-shell/ominx-desktop build/login/
for name in ominx-login ominx-seat ominx-passwd ominx-login-probe; do
    make "build/$name"
    cp "build/$name" build/login/
done
python3 - <<'PY'
import importlib.util, json, sys
from pathlib import Path
sys.argv = ['ominx-hash.py']
spec = importlib.util.spec_from_file_location('hashing', 'scripts/ominx-hash.py')
hashing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hashing)
spec = importlib.util.spec_from_file_location('archive', 'scripts/make-initramfs.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)
# Live demonstration credentials for the bootable media; recovery can change them.
password = Path('desktop/desktop-shell/demo-password').read_text().strip()
accounts = ''.join(
    f'{name}:{uid}:{uid}:/home/{name}:/bin/ominx-desktop:{locked}:'
    f'{hashing.generate(password, salt) if not locked else "!"}\n'
    for name, uid, salt, locked in (('ominx', 1000, 'OMINXliveDemo00', 0), ('guest', 1002, 'OMINXguestSalt0', 1)))
Path('build/login/accounts').write_text(accounts)
packaging.account_records('build/login/accounts')
for name in packaging.LOGIN_BINARIES + ('ominx-login-probe',):
    packaging.static_elf(Path('build/login') / name)
print('login bundle ready:', ' '.join(sorted(p.name for p in Path('build/login').iterdir())))
PY
cp LICENSE build/login/LICENSE
python3 - <<'PY'
from pathlib import Path
licenses = Path('build/sources/qtbase/LICENSES')
Path('build/login/QTBASE-LICENSES').write_bytes(b''.join(
    b'===== ' + p.name.encode() + b' =====\n' + p.read_bytes() + b'\n'
    for p in sorted(licenses.iterdir()) if p.is_file()))
PY
mkdir -p build/provenance
"build/toolchain/bin/$TARGET-readelf" -l build/login/ominx-desktop > build/provenance/desktop-shell-elf.txt
sha256sum build/login/ominx-desktop build/login/ominx-login build/login/ominx-seat \
          build/login/ominx-passwd build/login/ominx-login-probe > build/provenance/login-bundle.sha256
