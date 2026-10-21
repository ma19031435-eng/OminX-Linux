#!/bin/sh
# Source-only shared graphics SDK. Host tools and target sysroot are disjoint.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
. desktop/bus/source.env
. desktop/graphics/source.env
CROSS="$ROOT/build/toolchain/bin/$TARGET-"
SYS="$ROOT/build/graphics-sysroot"
HOST="$ROOT/build/graphics-host"
MESON=${MESON:-meson}
case $(readlink -f "$("${CROSS}gcc" -print-file-name=libc.a)") in
 "$ROOT/build/toolchain/"*) ;; *) echo 'Refusing host libc' >&2; exit 1;;
esac
mkdir -p "$SYS/usr" "$HOST" build/provenance build/sources
python3 - <<'PY'
import json, subprocess
for name, source in json.load(open('desktop/graphics/sources.json')).items():
    subprocess.run(['python3','scripts/fetch-archive.py',source['url'],source['sha256'],'build/sources/graphics-'+name, '--allow-internal-file-links', '--max-unpacked-mib=512'],check=True)
PY
scripts/fetch-source.sh https://github.com/libexpat/libexpat.git "$EXPAT_TAG" "$EXPAT_COMMIT" "$ROOT/build/sources/expat"
scripts/fetch-source.sh https://github.com/xkbcommon/libxkbcommon.git "$XKBCOMMON_TAG" "$XKBCOMMON_COMMIT" "$ROOT/build/sources/graphics-xkbcommon"
# Native scanner's XML dependency is also built from source, not target packages.
cmake -S build/sources/expat/expat -B build/graphics-host-expat -G Ninja \
 -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$HOST" -DCMAKE_INSTALL_LIBDIR=lib \
 -DEXPAT_SHARED_LIBS=OFF -DEXPAT_BUILD_TOOLS=OFF -DEXPAT_BUILD_TESTS=OFF -DEXPAT_BUILD_EXAMPLES=OFF -DEXPAT_BUILD_DOCS=OFF
cmake --build build/graphics-host-expat --parallel "${JOBS:-4}"
cmake --install build/graphics-host-expat
export PKG_CONFIG_LIBDIR="$HOST/lib/pkgconfig"
export PKG_CONFIG_PATH=
unset PKG_CONFIG_SYSROOT_DIR
"$MESON" setup build/graphics-wayland-host build/sources/graphics-wayland --prefix="$HOST" --libdir=lib \
 -Dlibraries=false -Dscanner=true -Ddtd_validation=false -Dtests=false -Ddocumentation=false
"$MESON" compile -C build/graphics-wayland-host -j "${JOBS:-4}"
"$MESON" install -C build/graphics-wayland-host
cat > build/graphics-native.ini <<CONFIG
[binaries]
pkg-config = ['env', 'PKG_CONFIG_LIBDIR=$HOST/lib/pkgconfig', 'PKG_CONFIG_SYSROOT_DIR=', 'pkg-config']
wayland-scanner = '$HOST/bin/wayland-scanner'
CONFIG
cat > build/graphics-cross.ini <<CONFIG
[binaries]
c = '${CROSS}gcc'
cpp = '${CROSS}g++'
ar = '${CROSS}ar'
strip = '${CROSS}strip'
pkg-config = 'pkg-config'
[properties]
needs_exe_wrapper = true
sys_root = '$SYS'
pkg_config_libdir = ['$SYS/usr/lib/pkgconfig', '$SYS/usr/share/pkgconfig']
[built-in options]
default_library = 'shared'
[host_machine]
system = 'linux'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
CONFIG
cat > build/graphics-toolchain.cmake <<CONFIG
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER "${CROSS}gcc")
set(CMAKE_CXX_COMPILER "${CROSS}g++")
set(CMAKE_FIND_ROOT_PATH "$SYS" "$ROOT/build/toolchain/$TARGET")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_SKIP_INSTALL_RPATH ON)
CONFIG
export PKG_CONFIG_LIBDIR="$SYS/usr/lib/pkgconfig:$SYS/usr/share/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="$SYS"
export PATH="$HOST/bin:$PATH"
cmake -S build/sources/graphics-zlib -B build/graphics-zlib -G Ninja \
 -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/graphics-toolchain.cmake" -DCMAKE_INSTALL_PREFIX=/usr \
 -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_BUILD_TYPE=Release -DZLIB_BUILD_TESTING=OFF
cmake --build build/graphics-zlib --parallel "${JOBS:-4}"
DESTDIR="$SYS" cmake --install build/graphics-zlib
cmake -S build/sources/expat/expat -B build/graphics-expat -G Ninja \
 -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/graphics-toolchain.cmake" -DCMAKE_INSTALL_PREFIX=/usr \
 -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_BUILD_TYPE=Release -DEXPAT_SHARED_LIBS=ON \
 -DEXPAT_BUILD_TOOLS=OFF -DEXPAT_BUILD_TESTS=OFF -DEXPAT_BUILD_EXAMPLES=OFF -DEXPAT_BUILD_DOCS=OFF
cmake --build build/graphics-expat --parallel "${JOBS:-4}"
DESTDIR="$SYS" cmake --install build/graphics-expat
mkdir -p build/graphics-libffi
(cd build/graphics-libffi && CC="${CROSS}gcc" CXX="${CROSS}g++" AR="${CROSS}ar" \
 "$ROOT/build/sources/graphics-libffi/configure" --host="$TARGET" --prefix=/usr --libdir=/usr/lib \
 --disable-static --enable-shared --disable-multi-os-directory --disable-docs && \
 make -j"${JOBS:-4}" && make DESTDIR="$SYS" install)
mbuild() {
 name=$1; shift
 "$MESON" setup "build/graphics-$name-target" "build/sources/graphics-$name" \
  --cross-file build/graphics-cross.ini --native-file build/graphics-native.ini \
  --prefix=/usr --libdir=lib --buildtype=release --wrap-mode=nofallback "$@"
 "$MESON" compile -C "build/graphics-$name-target" -j "${JOBS:-4}"
 DESTDIR="$SYS" "$MESON" install -C "build/graphics-$name-target"
}
mbuild wayland -Dlibraries=true -Dscanner=false -Ddtd_validation=false -Dtests=false -Ddocumentation=false
mbuild wayland-protocols -Dtests=false
mbuild xkeyboard-config
mbuild xkbcommon -Denable-tools=false -Denable-x11=false -Denable-docs=false \
 -Denable-wayland=false -Denable-xkbregistry=false -Denable-bash-completion=false -Dxkb-config-root=/usr/share/X11/xkb
mbuild libdrm -Dintel=disabled -Damdgpu=disabled -Dradeon=disabled -Dnouveau=disabled \
 -Dvmwgfx=disabled -Dfreedreno=disabled -Dtegra=disabled -Dvc4=disabled -Detnaviv=disabled \
 -Dexynos=disabled -Domap=disabled -Dudev=false -Dtests=false -Dman-pages=disabled -Dcairo-tests=disabled -Dvalgrind=disabled
mbuild mesa -Dgallium-drivers=softpipe -Dvulkan-drivers= -Dplatforms=wayland \
 -Dglx=disabled -Degl=enabled -Dgbm=enabled -Dgles1=disabled -Dgles2=enabled \
 -Dllvm=disabled -Dgallium-rusticl=false -Dglvnd=disabled -Dbuild-tests=false \
 -Dvideo-codecs= -Dgallium-va=disabled -Dgallium-vdpau=disabled \
 -Dvalgrind=disabled -Dlibunwind=disabled -Dzstd=disabled -Dmicrosoft-clc=disabled
"${CROSS}gcc" -O2 -Wall -Wextra -Werror src/graphics/probe.c \
 $(pkg-config --cflags --libs egl glesv2 wayland-client wayland-server xkbcommon libdrm) \
 -Wl,-rpath-link,"$SYS/usr/lib" -Wl,--dynamic-linker=/lib/ld-musl-x86_64.so.1 -o build/ominx-render-probe
python3 scripts/stage-graphics-runtime.py
cp desktop/graphics/sources.json desktop/graphics/source.env build/graphics-cross.ini build/graphics-native.ini build/graphics-toolchain.cmake build/provenance/
