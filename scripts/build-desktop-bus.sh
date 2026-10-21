#!/bin/sh
# Build upstream IPC dependencies and original supervisor/probe; no target packages.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
. desktop/bus/source.env
PREFIX="$ROOT/build/toolchain/bin/$TARGET-"
STAGE="$ROOT/build/bus-prefix"
MESON=${MESON:-meson}
case $(readlink -f "$("${PREFIX}gcc" -print-file-name=libc.a)") in
    "$ROOT/build/toolchain/"*) ;;
    *) echo 'Refusing libc outside the source toolchain' >&2; exit 1 ;;
esac
mkdir -p build/sources build/provenance build/desktop-bus "$STAGE"
scripts/fetch-source.sh https://github.com/libexpat/libexpat.git "$EXPAT_TAG" "$EXPAT_COMMIT" "$ROOT/build/sources/expat"
python3 scripts/fetch-archive.py "$DBUS_URL" "$DBUS_SHA256" "$ROOT/build/sources/dbus-$DBUS_VERSION"
cat > build/bus-toolchain.cmake <<CONFIG
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER "${PREFIX}gcc")
set(CMAKE_FIND_ROOT_PATH "$ROOT/build/toolchain/$TARGET" "$STAGE")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static")
CONFIG
cmake -S build/sources/expat/expat -B build/expat-target -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/bus-toolchain.cmake" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$STAGE" -DCMAKE_INSTALL_LIBDIR=lib \
    -DEXPAT_SHARED_LIBS=OFF -DEXPAT_BUILD_TOOLS=OFF -DEXPAT_BUILD_EXAMPLES=OFF \
    -DEXPAT_BUILD_TESTS=OFF -DEXPAT_BUILD_DOCS=OFF
cmake --build build/expat-target --parallel "${JOBS:-2}"
cmake --install build/expat-target
cat > build/bus-cross.ini <<CONFIG
[binaries]
c = '${PREFIX}gcc'
ar = '${PREFIX}ar'
strip = '${PREFIX}strip'
pkg-config = 'pkg-config'
[properties]
needs_exe_wrapper = true
pkg_config_libdir = '$STAGE/lib/pkgconfig'
[built-in options]
c_link_args = ['-static']
default_library = 'static'
[host_machine]
system = 'linux'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
CONFIG
export PKG_CONFIG_LIBDIR="$STAGE/lib/pkgconfig"
export PKG_CONFIG_PATH=
reconfigure=
[ ! -f build/dbus-target/meson-private/coredata.dat ] || reconfigure=--reconfigure
"$MESON" setup $reconfigure build/dbus-target "build/sources/dbus-$DBUS_VERSION" \
    --cross-file build/bus-cross.ini --prefix="$STAGE" --libdir=lib \
    --sysconfdir=/etc --localstatedir=/var --datadir=/usr/share --buildtype=release \
    -Ddefault_library=static -Dprefer_static=true -Ddbus_user=messagebus \
    -Dapparmor=disabled -Dselinux=disabled -Dlibaudit=disabled -Dsystemd=disabled \
    -Dx11_autolaunch=disabled -Dlaunchd=disabled -Duser_session=false \
    -Ddoxygen_docs=disabled -Dducktype_docs=disabled -Dxml_docs=disabled -Dqt_help=disabled \
    -Dmodular_tests=disabled -Dinstalled_tests=false -Dintrusive_tests=false \
    -Druntime_dir=/run -Dsystem_socket=/run/dbus/system_bus_socket \
    -Dsystem_pid_file=/run/dbus/dbus.pid -Dsession_socket_dir=/tmp
"$MESON" compile -C build/dbus-target -j "${JOBS:-2}"
DESTDIR="$ROOT/build/bus-install" "$MESON" install -C build/dbus-target
cp -a "$ROOT/build/bus-install$STAGE/." "$STAGE/"
cp build/dbus-target/bus/dbus-daemon build/desktop-bus/dbus-daemon
"${PREFIX}gcc" -static -O2 -Wall -Wextra -Werror src/bus/supervisor.c -o build/desktop-bus/ominx-desktop-bus
# pkg-config is constrained to this source-built prefix, never host libdbus.
"${PREFIX}gcc" -static -O2 -Wall -Wextra -Werror src/bus/probe.c \
    $(pkg-config --cflags --libs --static dbus-1) -o build/desktop-bus/ominx-bus-probe
cp "build/sources/dbus-$DBUS_VERSION/COPYING" build/desktop-bus/DBUS-COPYING
cp "build/sources/dbus-$DBUS_VERSION/LICENSES/AFL-2.1.txt" build/desktop-bus/DBUS-AFL-2.1.txt
cp "build/sources/dbus-$DBUS_VERSION/LICENSES/GPL-2.0-or-later.txt" build/desktop-bus/DBUS-GPL-2.0-or-later.txt
cp build/sources/expat/expat/COPYING build/desktop-bus/EXPAT-COPYING
python3 - <<'PYLICENSE'
from pathlib import Path
source = Path('build/sources/dbus-1.16.2/LICENSES')
Path('build/desktop-bus/DBUS-LICENSES').write_bytes(b''.join(
    b'===== ' + path.name.encode() + b' =====\n' + path.read_bytes() + b'\n'
    for path in sorted(source.iterdir()) if path.is_file()))
PYLICENSE
cp "build/downloads/$DBUS_SHA256.tar" "build/provenance/dbus-$DBUS_VERSION.tar.xz"
git -C build/sources/expat archive --format=tar.gz --output="$ROOT/build/provenance/expat-source.tar.gz" "$EXPAT_COMMIT"
cp desktop/bus/source.env build/provenance/desktop-bus-source.env
cp build/bus-cross.ini build/bus-toolchain.cmake build/provenance/
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('archive', 'scripts/make-initramfs.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
for name in ('dbus-daemon', 'ominx-desktop-bus', 'ominx-bus-probe'):
    m.static_elf('build/desktop-bus/' + name)
PY
sha256sum build/desktop-bus/* > build/provenance/desktop-bus.sha256
