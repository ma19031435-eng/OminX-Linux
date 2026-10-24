#!/bin/sh
# OminX source-built Wine/Proton runtime (LFS order).
#
# The OminX target itself is musl. Windows programs cannot run on it
# directly: Wine requires a glibc environment. This script therefore
# builds, entirely from pinned upstream source, an isolated glibc prefix
# for /usr/lib/ominx/wine-runtime in the same layering a Linux From
# Scratch system uses:
#
#   kernel headers -> glibc -> zlib/expat/libffi -> Wayland ->
#   FreeType/fontconfig/libpng -> ALSA -> Vulkan headers/loader ->
#   Wine (new WoW64: 32-bit and 64-bit programs from one build) ->
#   DXVK + vkd3d-proton (the Direct3D half of a Proton-style setup)
#
# Build-host tools only (never shipped): host GCC/binutils targeting
# x86_64-linux-gnu, MinGW cross compilers for the Windows-side PE code,
# meson/cmake/autotools, patchelf. Every shipped byte is built here
# from the pinned sources, and scripts/stage-wine-runtime.py audits the
# result before it can be packaged: any host library leaking into the
# tree fails the build instead of a user's first double-click.
#
# Run on the CI builder (it takes hours):
#   MESON=$PWD/build/meson-env/bin/meson JOBS=4 scripts/build-wine-runtime.sh
# Output: build/wine-runtime/ (ready for make-initramfs --wine-runtime-dir)
#
# Staging trick: during the build, ELF interpreters point at the staged
# loader by its build-machine path so build-time tools (wayland-scanner,
# Wine's widl/wrc) execute. The final step rewrites interpreters and
# library paths to the target prefix with patchelf; the audit proves it.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. compat/sources.env
. toolchain/sources.env
FP=$WINE_RUNTIME_PREFIX
WORK="$ROOT/build/wine-rt"
SRC="$ROOT/build/sources/wine-rt"
STAGE="$WORK/stage"            # DESTDIR root; the prefix lives under $STAGE$FP
SFP="$STAGE$FP"                # staged prefix (build-machine path)
STAMPS="$WORK/stamps"
OUT="$ROOT/build/wine-runtime"
JOBS=${JOBS:-4}
MESON=${MESON:-meson}

for tool in gcc g++ make cmake pkg-config patchelf flex bison gperf \
            x86_64-w64-mingw32-gcc i686-w64-mingw32-gcc \
            autoreconf "$MESON"; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Missing build-host tool: $tool" >&2
        echo "On the CI image these come from apt/pip as build tools only." >&2
        exit 1
    }
done
if [ "$(gcc -dumpmachine)" != "x86_64-linux-gnu" ]; then
    echo "The host compiler must target x86_64-linux-gnu" >&2
    exit 1
fi
mkdir -p "$SRC" "$SFP/lib" "$SFP/include" "$SFP/usr/include" "$STAMPS" "$WORK/bin"

# Compiler wrappers: never the host libc, always the staged one.
RTCC="$WORK/bin/rtcc"
cat > "$RTCC" <<WRAP
#!/bin/sh
# --sysroot maps the absolute paths inside glibc's linker scripts
# (libc.so, libm.so: /usr/lib/ominx/wine-runtime/...) onto the stage.
exec gcc --sysroot="$STAGE" -nostdinc \\
    -isystem "$SFP/usr/include" -isystem "$SFP/include" \\
    -isystem "$(gcc -print-file-name=include)" \\
    -B"$SFP/lib/" -L"$SFP/lib" \\
    -Wl,--dynamic-linker,"$SFP/lib/ld-linux-x86-64.so.2" \\
    -Wl,-rpath,"$SFP/lib" "\$@"
WRAP
chmod +x "$RTCC"
export PKG_CONFIG_LIBDIR="$SFP/lib/pkgconfig:$SFP/share/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="$STAGE"
unset PKG_CONFIG_PATH || true

done_stage() { [ -f "$STAMPS/$1" ]; }
mark_stage() { : > "$STAMPS/$1"; echo "ominx-wine-runtime: $1 done"; }
fetch_git() { scripts/fetch-source.sh "$1" "$2" "$3" "$SRC/$4"; }

# ---------------------------------------------------------------- sources
if ! done_stage sources; then
    fetch_git "$GLIBC_REPO" "$GLIBC_TAG" "$GLIBC_COMMIT" glibc
    fetch_git "$WINE_REPO" "$WINE_TAG" "$WINE_COMMIT" wine
    fetch_git "$FREETYPE_REPO" "$FREETYPE_TAG" "$FREETYPE_COMMIT" freetype
    fetch_git "$FONTCONFIG_REPO" "$FONTCONFIG_TAG" "$FONTCONFIG_COMMIT" fontconfig
    fetch_git "$EXPAT_REPO" "$EXPAT_TAG" "$EXPAT_COMMIT" expat
    fetch_git "$ZLIB_REPO" "$ZLIB_TAG" "$ZLIB_COMMIT" zlib
    fetch_git "$LIBPNG_REPO" "$LIBPNG_TAG" "$LIBPNG_COMMIT" libpng
    fetch_git "$ALSA_REPO" "$ALSA_TAG" "$ALSA_COMMIT" alsa-lib
    fetch_git "$VKHEADERS_REPO" "$VKHEADERS_TAG" "$VKHEADERS_COMMIT" vulkan-headers
    fetch_git "$VKLOADER_REPO" "$VKLOADER_TAG" "$VKLOADER_COMMIT" vulkan-loader
    fetch_git "$DXVK_REPO" "$DXVK_TAG" "$DXVK_COMMIT" dxvk
    fetch_git "$VKD3D_REPO" "$VKD3D_TAG" "$VKD3D_COMMIT" vkd3d-proton
    python3 - <<'PY'
import json, subprocess
for name, source in json.load(open('compat/sources.json')).items():
    if name == 'zlib':  # pinned as git in compat/sources.env (ZLIB_*)
        continue
    subprocess.run(['python3', 'scripts/fetch-archive.py', source['url'], source['sha256'],
                    'build/sources/wine-rt/' + name, '--max-unpacked-mib=512',
                    '--max-download-mib=128'], check=True)
PY
    git -C "$SRC/dxvk" submodule update --init --recursive --depth 1
    git -C "$SRC/vkd3d-proton" submodule update --init --recursive --depth 1
    mark_stage sources
fi

# ------------------------------------------------------- headers + glibc
if ! done_stage headers; then
    scripts/fetch-source.sh https://github.com/gregkh/linux.git \
        "$LINUX_TAG" "$LINUX_COMMIT" "$ROOT/build/sources/linux"
    make -C "$ROOT/build/sources/linux" ARCH=x86_64 \
        INSTALL_HDR_PATH="$SFP/usr" headers_install >/dev/null
    mark_stage headers
fi
if ! done_stage glibc; then
    mkdir -p "$WORK/glibc-build"
    cd "$WORK/glibc-build"
    # glibc is its own build system: it does not consume host headers for
    # target code. libc_cv_slibdir pins the loader into the final prefix.
    BUILD_CC=gcc CC=gcc \
    "$SRC/glibc/configure" --prefix="$FP" --host=x86_64-linux-gnu \
        --build="$(gcc -dumpmachine)" --with-headers="$SFP/usr/include" \
        --disable-werror --disable-multi-arch --enable-kernel=6.1 \
        libc_cv_slibdir="$FP/lib" libc_cv_rtlddir="$FP/lib"
    make -j"$JOBS"
    make install_root="$STAGE" install
    cd "$ROOT"
    mark_stage glibc
fi
# The staged loader must be usable by the wrappers from here on.
test -x "$SFP/lib/ld-linux-x86-64.so.2" || {
    echo "glibc stage did not install the dynamic loader" >&2; exit 1; }
if ! done_stage glibc-smoke; then
    printf 'int main(void){return 42;}\n' > "$WORK/smoke.c"
    "$RTCC" -O2 "$WORK/smoke.c" -o "$WORK/smoke"
    rc=0
    "$WORK/smoke" || rc=$?
    if [ "$rc" -ne 42 ]; then
        echo "staged glibc hello-world returned $rc, expected 42" >&2
        exit 1
    fi
    mark_stage glibc-smoke
fi

meson_rt() { # meson_rt <name> <srcdir> <extra args...>
    name=$1; src=$2; shift 2
    "$MESON" setup "$WORK/$name-build" "$src" --prefix="$FP" \
        --libdir=lib --buildtype=release "$@" >/dev/null
    "$MESON" compile -C "$WORK/$name-build" -j "$JOBS" >/dev/null
    DESTDIR="$STAGE" "$MESON" install -C "$WORK/$name-build" >/dev/null
}
export CC="$RTCC"
export LDFLAGS="-Wl,-rpath,$SFP/lib"

# ---------------------------------------------------------------- base libs
if ! done_stage zlib; then
    cd "$SRC/zlib"
    ./configure --prefix="$FP" --libdir="$FP/lib" >/dev/null
    make -j"$JOBS" >/dev/null && make DESTDIR="$STAGE" install >/dev/null
    cd "$ROOT"; mark_stage zlib
fi
if ! done_stage expat; then
    cmake -S "$SRC/expat/expat" -B "$WORK/expat-build" \
        -DCMAKE_INSTALL_PREFIX="$FP" -DCMAKE_INSTALL_LIBDIR=lib \
        -DCMAKE_C_COMPILER="$RTCC" -DEXPAT_BUILD_TOOLS=OFF \
        -DEXPAT_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build "$WORK/expat-build" -j "$JOBS" >/dev/null
    DESTDIR="$STAGE" cmake --install "$WORK/expat-build" >/dev/null
    mark_stage expat
fi
if ! done_stage libffi; then
    cd "$SRC/libffi"
    ./configure --prefix="$FP" --libdir="$FP/lib" --disable-exec-static-tramp >/dev/null
    make -j"$JOBS" >/dev/null && make DESTDIR="$STAGE" install >/dev/null
    cd "$ROOT"; mark_stage libffi
fi
if ! done_stage wayland; then
    meson_rt wayland "$SRC/wayland" -Ddocumentation=false -Ddtd_validation=false \
        -Dtests=false -Dscanner=true -Dlibraries=true
    mark_stage wayland
fi
if ! done_stage freetype; then
    meson_rt freetype "$SRC/freetype" -Dzlib=enabled -Dpng=disabled \
        -Dbzip2=disabled -Dbrotli=disabled -Dharfbuzz=disabled
    mark_stage freetype
fi
if ! done_stage libpng; then
    cd "$SRC/libpng"
    [ -x configure ] || autoreconf -fi >/dev/null
    CPPFLAGS="-I$SFP/include" ./configure --prefix="$FP" --libdir="$FP/lib" >/dev/null
    make -j"$JOBS" >/dev/null && make DESTDIR="$STAGE" install >/dev/null
    cd "$ROOT"; mark_stage libpng
fi
if ! done_stage fontconfig; then
    meson_rt fontconfig "$SRC/fontconfig" -Ddoc=disabled -Dtests=disabled \
        -Dtools=disabled -Dcache-build=disabled -Diconv=disabled
    mark_stage fontconfig
fi
if ! done_stage alsa; then
    cd "$SRC/alsa-lib"
    [ -x configure ] || autoreconf -fi >/dev/null
    ./configure --prefix="$FP" --libdir="$FP/lib" --disable-python \
        --without-libdl >/dev/null
    make -j"$JOBS" >/dev/null && make DESTDIR="$STAGE" install >/dev/null
    cd "$ROOT"; mark_stage alsa
fi
if ! done_stage vulkan; then
    cmake -S "$SRC/vulkan-headers" -B "$WORK/vkheaders-build" \
        -DCMAKE_INSTALL_PREFIX="$FP" >/dev/null
    DESTDIR="$STAGE" cmake --install "$WORK/vkheaders-build" >/dev/null
    # Static libstdc++/libgcc: this tree ships no host C++ runtime.
    cmake -S "$SRC/vulkan-loader" -B "$WORK/vkloader-build" \
        -DCMAKE_INSTALL_PREFIX="$FP" -DCMAKE_INSTALL_LIBDIR=lib \
        -DCMAKE_C_COMPILER="$RTCC" \
        -DCMAKE_CXX_COMPILER=g++ \
        -DCMAKE_CXX_FLAGS="-static-libstdc++ -static-libgcc" \
        -DVULKAN_HEADERS_INSTALL_DIR="$SFP" \
        -DBUILD_WSI_WAYLAND_SUPPORT=ON -DBUILD_WSI_XCB_SUPPORT=OFF \
        -DBUILD_WSI_XLIB_SUPPORT=OFF -DBUILD_TESTS=OFF \
        -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build "$WORK/vkloader-build" -j "$JOBS" >/dev/null
    DESTDIR="$STAGE" cmake --install "$WORK/vkloader-build" >/dev/null
    mark_stage vulkan
fi

# --------------------------------------------------------------------- Wine
if ! done_stage wine; then
    mkdir -p "$WORK/wine-build"
    cd "$SRC/wine"
    [ -x configure ] || autoreconf -f >/dev/null
    cd "$WORK/wine-build"
    # Wayland-first (the OminX desktop is Wayland/Qt), Vulkan for DXVK,
    # new WoW64 so 32-bit programs need no 32-bit host libraries.
    "$SRC/wine/configure" --prefix="$FP" \
        --enable-archs=i386,x86_64 \
        --with-wayland --with-vulkan --with-alsa --with-freetype \
        --with-fontconfig \
        --without-x --without-opengl --without-gstreamer --without-dbus \
        --without-cups --without-sane --without-v4l2 --without-pcap \
        --without-netapi --without-udev --without-unwind
    make -j"$JOBS"
    make DESTDIR="$STAGE" install
    cd "$ROOT"
    mark_stage wine
fi

# ------------------------------------------------- DXVK and vkd3d-proton
# PE DLLs built with the build-host MinGW compilers (tools only). Their
# C++ runtimes are statically linked by their upstream build defaults.
meson_mingw() { # meson_mingw <name> <srcdir> <cross> <subdir with dlls> <dest share subdir>
    name=$1; src=$2; cross=$3; dlls=$4; dest=$5; shift 5
    "$MESON" setup "$WORK/$name-build" "$src" --cross-file "$cross" \
        --buildtype=release --strip "$@" >/dev/null
    "$MESON" compile -C "$WORK/$name-build" -j "$JOBS" >/dev/null
    mkdir -p "$SFP/share/$dest"
    for dll in "$WORK/$name-build/$dlls"/*.dll; do
        if [ -f "$dll" ]; then cp "$dll" "$SFP/share/$dest/"; fi
    done
}
if ! done_stage dxvk; then
    meson_mingw dxvk64 "$SRC/dxvk" "$SRC/dxvk/build-win64.txt" src/dxvk dxvk-temp
    mkdir -p "$SFP/share/dxvk/x64" "$SFP/share/dxvk/x32"
    # DXVK emits the D3D front-end DLLs from src/{d3d9,d3d10,d3d11,dxgi}.
    for part in d3d8 d3d9 d3d10 d3d11 dxgi; do
        for dll in "$WORK/dxvk64-build/src/$part"/*.dll; do
            [ -f "$dll" ] && cp "$dll" "$SFP/share/dxvk/x64/"
        done
    done
    meson_mingw dxvk32 "$SRC/dxvk" "$SRC/dxvk/build-win32.txt" src/dxvk dxvk-temp32
    for part in d3d8 d3d9 d3d10 d3d11 dxgi; do
        for dll in "$WORK/dxvk32-build/src/$part"/*.dll; do
            [ -f "$dll" ] && cp "$dll" "$SFP/share/dxvk/x32/"
        done
    done
    rm -rf "$SFP/share/dxvk-temp" "$SFP/share/dxvk-temp32"
    mark_stage dxvk
fi
if ! done_stage vkd3d; then
    cat > "$WORK/vkd3d-cross64.ini" <<'CROSS'
[binaries]
c = 'x86_64-w64-mingw32-gcc'
cpp = 'x86_64-w64-mingw32-g++'
ar = 'x86_64-w64-mingw32-ar'
strip = 'x86_64-w64-mingw32-strip'
windres = 'x86_64-w64-mingw32-windres'
[host_machine]
system = 'windows'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
CROSS
    sed 's/x86_64-w64-mingw32/i686-w64-mingw32/g; s/cpu_family = .x86_64./cpu_family = '"'"'x86'"'"'/; s/cpu = .x86_64./cpu = '"'"'i686'"'"'/' \
        "$WORK/vkd3d-cross64.ini" > "$WORK/vkd3d-cross32.ini"
    # vkd3d-proton 2.14 builds d3d12.dll and d3d12core.dll in libs/d3d12 and
    # libs/d3d12core. libs/vkd3d and libs/vkd3d-common build no DLLs.
    meson_mingw vkd3d64 "$SRC/vkd3d-proton" "$WORK/vkd3d-cross64.ini" libs/d3d12 vkd3d-temp \
        -Denable_tests=false
    meson_mingw vkd3d32 "$SRC/vkd3d-proton" "$WORK/vkd3d-cross32.ini" libs/d3d12 vkd3d-temp32 \
        -Denable_tests=false
    mkdir -p "$SFP/share/vkd3d-proton/x64" "$SFP/share/vkd3d-proton/x86"
    for dll in "$WORK"/vkd3d64-build/libs/d3d12/*.dll "$WORK"/vkd3d64-build/libs/d3d12core/*.dll; do
        [ -f "$dll" ] && cp "$dll" "$SFP/share/vkd3d-proton/x64/"
    done
    for dll in "$WORK"/vkd3d32-build/libs/d3d12/*.dll "$WORK"/vkd3d32-build/libs/d3d12core/*.dll; do
        [ -f "$dll" ] && cp "$dll" "$SFP/share/vkd3d-proton/x86/"
    done
    # An empty DLL set is a build failure, never a silent warning.
    for dll in x64/d3d12.dll x64/d3d12core.dll x86/d3d12.dll x86/d3d12core.dll; do
        test -f "$SFP/share/vkd3d-proton/$dll" || { echo "vkd3d-proton did not produce $dll" >&2; exit 1; }
    done
    rm -rf "$SFP/share/vkd3d-temp" "$SFP/share/vkd3d-temp32"
    mark_stage vkd3d
fi

# ------------------------------------------------------------- finalization
echo "ominx-wine-runtime: assembling $OUT"
rm -rf "$OUT"
mkdir -p "$OUT"
cp -a "$SFP/." "$OUT/"
# Headers, static libraries and documentation are build inputs, not the
# runtime; /bin and the Wine data trees stay complete.
rm -rf "$OUT/include" "$OUT/usr" "$OUT/share/man" "$OUT/share/doc" \
       "$OUT/lib/pkgconfig" "$OUT/share/pkgconfig"
find "$OUT" -name '*.a' -delete
find "$OUT" -name '*.la' -delete
printf 'wine-%s\nominx-runtime=1\ndxvk=%s\nvkd3d-proton=%s\n' \
    "$WINE_VERSION" "$DXVK_TAG" "$VKD3D_TAG" > "$OUT/VERSION"
test -x "$OUT/lib/ld-linux-x86-64.so.2"
test -x "$OUT/bin/wine"
if [ ! -e "$OUT/bin/wine64" ]; then ln -s wine "$OUT/bin/wine64"; fi
# Wine normally installs its own wineserver into bin/. Only fall back to a
# link if a future layout moves it; ominx-wined can also use the builtin.
if [ ! -e "$OUT/bin/wineserver" ] && [ -x "$OUT/lib/wine/x86_64-unix/wineserver" ]; then
    ln -s ../lib/wine/x86_64-unix/wineserver "$OUT/bin/wineserver"
fi
# Rewrite build-machine paths to the target prefix, then prove it.
find "$OUT" -type f | while read -r file; do
    if readelf -h "$file" >/dev/null 2>&1; then
        patchelf --set-rpath "$FP/lib:\$ORIGIN/../lib" "$file" 2>/dev/null || true
        if [ -x "$file" ]; then
            case "$(patchelf --print-interpreter "$file" 2>/dev/null || true)" in
                '') ;;
                *) patchelf --set-interpreter "$FP/lib/ld-linux-x86-64.so.2" "$file" ;;
            esac
        fi
    fi
done
python3 - <<'PY'
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('stage', 'scripts/stage-wine-runtime.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
nodes = stage.audit('build/wine-runtime')
print(f"wine runtime audit: {len(nodes)} files, self-contained under {stage.PREFIX}")
PY
mkdir -p build/provenance
cp compat/sources.env compat/sources.json build/provenance/
(cd "$OUT" && find . -type f -exec sha256sum {} + | sort) > build/provenance/wine-runtime.sha256
echo "ominx-wine-runtime: ready at $OUT (VERSION: $(cat "$OUT/VERSION" | head -1))"
