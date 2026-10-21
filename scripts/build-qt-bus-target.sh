#!/bin/sh
# Isolated Core/DBus bootstrap; does not mutate accepted framebuffer/Quick builds.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
. desktop/qt/source.env
PREFIX="$ROOT/build/toolchain/bin/$TARGET-"
BUS="$ROOT/build/bus-prefix"
HOST="$ROOT/build/qt-bus-host"
STAGE="$ROOT/build/qt-bus-prefix"
BUILD="$ROOT/build/qt-bus-target"
SRC="$ROOT/build/sources/qtbase"
case $(readlink -f "$("${PREFIX}gcc" -print-file-name=libc.a)") in
    "$ROOT/build/toolchain/"*) ;;
    *) echo 'Refusing host libc' >&2; exit 1 ;;
esac
[ -f "$BUS/lib/libdbus-1.a" ] || { echo 'Build source IPC dependencies first' >&2; exit 1; }
mkdir -p build/provenance
scripts/fetch-source.sh https://github.com/qt/qtbase.git "$QT_TAG" "$QTBASE_COMMIT" "$SRC"
cmake -S "$SRC" -B "$HOST" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF -DFEATURE_developer_build=ON \
    -DFEATURE_gui=OFF -DFEATURE_widgets=OFF -DFEATURE_dbus=ON -DINPUT_dbus=runtime -DFEATURE_icu=OFF
cmake --build "$HOST" --target host_tools --parallel "${JOBS:-2}"
cat > build/qt-bus-musl.cmake <<CONFIG
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER "${PREFIX}gcc")
set(CMAKE_CXX_COMPILER "${PREFIX}g++")
set(CMAKE_FIND_ROOT_PATH "$ROOT/build/toolchain/$TARGET" "$BUS" "$STAGE")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static")
CONFIG
export PKG_CONFIG_LIBDIR="$BUS/lib/pkgconfig"
export PKG_CONFIG_PATH=
cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-bus-musl.cmake" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$STAGE" -DCMAKE_PREFIX_PATH="$BUS" -DQT_HOST_PATH="$HOST" \
    -DBUILD_SHARED_LIBS=OFF -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF \
    -DFEATURE_gui=OFF -DFEATURE_widgets=OFF -DFEATURE_network=OFF -DFEATURE_sql=OFF \
    -DFEATURE_dbus=ON -DFEATURE_dbus_linked=ON -DINPUT_dbus=linked \
    -DFEATURE_glib=OFF -DFEATURE_icu=OFF -DFEATURE_openssl=OFF \
    -DFEATURE_system_zlib=OFF -DFEATURE_system_pcre2=OFF -DFEATURE_zstd=OFF -DFEATURE_brotli=OFF
cmake --build "$BUILD" --parallel "${JOBS:-2}"
cmake --install "$BUILD"
cmake -S desktop/qt-bus-probe -B build/qt-bus-probe -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-bus-musl.cmake" -DCMAKE_PREFIX_PATH="$STAGE;$BUS" \
    -DQT_HOST_PATH="$HOST" -DCMAKE_BUILD_TYPE=Release
cmake --build build/qt-bus-probe --parallel "${JOBS:-2}"
python3 - <<'PY'
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('archive', 'scripts/make-initramfs.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.static_elf('build/qt-bus-probe/ominx-qt-bus-probe')
licenses = Path('build/sources/qtbase/LICENSES')
Path('build/qt-bus-probe/QTBASE-LICENSES').write_bytes(b''.join(
    b'===== ' + p.name.encode() + b' =====\n' + p.read_bytes() + b'\n'
    for p in sorted(licenses.iterdir()) if p.is_file()))
PY
cp "$BUILD/config.summary" build/provenance/qt-bus-config.summary
cp desktop/qt/source.env build/provenance/qt-bus-source.env
cp build/qt-bus-musl.cmake build/provenance/
git -C "$SRC" archive --format=tar.gz --output="$ROOT/build/provenance/qtbase-source.tar.gz" "$QTBASE_COMMIT"
"${PREFIX}readelf" -l build/qt-bus-probe/ominx-qt-bus-probe > build/provenance/qt-bus-probe-elf.txt
sha256sum build/qt-bus-probe/ominx-qt-bus-probe > build/provenance/qt-bus-probe.sha256
