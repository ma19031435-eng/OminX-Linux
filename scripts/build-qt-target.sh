#!/bin/sh
# Bootstrap Qt host generators, then cross-build static Qt for the musl target.
# This first software framebuffer stage does NOT build Plasma or authentication.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
. desktop/qt/source.env
PREFIX="$ROOT/build/toolchain/bin/$TARGET-"
[ -x "${PREFIX}g++" ] || { echo 'Build the source C/C++ toolchain first' >&2; exit 1; }
case $(readlink -f "$("${PREFIX}gcc" -print-file-name=libc.a)") in
    "$ROOT/build/toolchain/"*) ;;
    *) echo 'Refusing a libc outside the source toolchain' >&2; exit 1 ;;
esac
SRC="$ROOT/build/sources/qtbase"
HOST="$ROOT/build/qt-host"
TARGET_BUILD="$ROOT/build/qt-target"
STAGE="$ROOT/build/qt-prefix"
mkdir -p build/sources build/provenance "$HOST" "$TARGET_BUILD" build/empty-pkgconfig
scripts/fetch-source.sh https://github.com/qt/qtbase.git "$QT_TAG" "$QTBASE_COMMIT" "$SRC"
# Host code generators are separate and are never packaged in the target image.
cmake -S "$SRC" -B "$HOST" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF \
    -DFEATURE_developer_build=ON -DFEATURE_gui=OFF \
    -DFEATURE_widgets=OFF -DFEATURE_dbus=OFF -DFEATURE_icu=OFF
cmake --build "$HOST" --target host_tools --parallel "${JOBS:-2}"
cat > build/qt-musl.cmake <<CONFIG
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER "${PREFIX}gcc")
set(CMAKE_CXX_COMPILER "${PREFIX}g++")
set(CMAKE_FIND_ROOT_PATH "$ROOT/build/toolchain/$TARGET" "$STAGE")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static")
CONFIG
# Never let pkg-config discover the build host's libraries for target linking.
export PKG_CONFIG_LIBDIR="$ROOT/build/empty-pkgconfig"
export PKG_CONFIG_PATH=
cmake -S "$SRC" -B "$TARGET_BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-musl.cmake" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$STAGE" \
    -DQT_HOST_PATH="$HOST" -DBUILD_SHARED_LIBS=OFF \
    -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF \
    -DFEATURE_opengl=OFF -DFEATURE_vulkan=OFF -DFEATURE_xcb=OFF \
    -DFEATURE_eglfs=OFF -DFEATURE_linuxfb=ON -DFEATURE_evdev=ON \
    -DFEATURE_libinput=OFF -DFEATURE_libudev=OFF \
    -DFEATURE_dbus=OFF -DFEATURE_glib=OFF -DFEATURE_icu=OFF \
    -DFEATURE_openssl=OFF -DFEATURE_cups=OFF -DFEATURE_fontconfig=OFF \
    -DFEATURE_system_freetype=OFF -DFEATURE_system_harfbuzz=OFF \
    -DFEATURE_system_png=OFF -DFEATURE_system_jpeg=OFF \
    -DFEATURE_system_zlib=OFF -DFEATURE_system_pcre2=OFF \
    -DFEATURE_zstd=OFF -DFEATURE_brotli=OFF
cmake --build "$TARGET_BUILD" --parallel "${JOBS:-2}"
cmake --install "$TARGET_BUILD"
cmake -S desktop/probe -B build/graphics-probe -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-musl.cmake" \
    -DCMAKE_PREFIX_PATH="$STAGE" -DQT_HOST_PATH="$HOST" -DCMAKE_BUILD_TYPE=Release
cmake --build build/graphics-probe --parallel "${JOBS:-2}"
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('archive', 'scripts/make-initramfs.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.static_elf('build/graphics-probe/ominx-graphics-probe')
PY
cp desktop/qt/source.env build/provenance/qt-source.env
cp build/qt-musl.cmake build/provenance/
cp "$TARGET_BUILD/config.summary" build/provenance/qt-config.summary
"${PREFIX}readelf" -l build/graphics-probe/ominx-graphics-probe > build/provenance/graphics-probe-elf.txt
sha256sum build/graphics-probe/ominx-graphics-probe > build/provenance/graphics-probe.sha256
