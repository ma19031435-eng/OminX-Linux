#!/bin/sh
# Next bootstrap layer: upstream Qt Quick, not a display manager or KDE session.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. desktop/qt/source.env
. desktop/qt/quick.env
. toolchain/sources.env
HOST="$ROOT/build/qt-host"
STAGE="$ROOT/build/qt-prefix"
[ -f "$STAGE/lib/cmake/Qt6Widgets/Qt6WidgetsConfig.cmake" ] || {
    echo 'Build the source-linked target Qt base first' >&2; exit 1;
}
for module in qtshadertools qtdeclarative; do
    case "$module" in
        qtshadertools) commit=$QTSHADERTOOLS_COMMIT ;;
        qtdeclarative) commit=$QTDECLARATIVE_COMMIT ;;
    esac
    scripts/fetch-source.sh "https://github.com/qt/$module.git" "$QT_TAG" "$commit" "$ROOT/build/sources/$module"
done
# qsb needs native Qt Gui. Upgrade only host generators; never install host code
# into the musl prefix. All rendering/font dependencies here are Qt's bundled sources.
cmake -S build/sources/qtbase -B "$HOST" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF \
    -DFEATURE_developer_build=ON -DFEATURE_gui=ON -DFEATURE_widgets=ON \
    -DINPUT_opengl=no -DFEATURE_opengl=OFF -DFEATURE_vulkan=OFF \
    -DFEATURE_xcb=OFF -DFEATURE_eglfs=OFF -DFEATURE_dbus=OFF -DFEATURE_icu=OFF \
    -DFEATURE_fontconfig=OFF -DFEATURE_system_freetype=OFF -DFEATURE_system_harfbuzz=OFF
cmake --build "$HOST" --parallel "${JOBS:-2}"
for module in qtshadertools qtdeclarative; do
    # No native Quick renderer is needed for code generation. Disabling animation
    # suppresses that optional subtree without disabling the target's Quick build.
    cmake -S "build/sources/$module" -B "build/$module-host" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$HOST" \
        -DCMAKE_INSTALL_PREFIX="$HOST" -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF \
        -DFEATURE_qml_animation=OFF
    cmake --build "build/$module-host" --parallel "${JOBS:-2}"
    cmake --install "build/$module-host"
done
export PKG_CONFIG_LIBDIR="$ROOT/build/empty-pkgconfig"
export PKG_CONFIG_PATH=
for module in qtshadertools qtdeclarative; do
    cmake -S "build/sources/$module" -B "build/$module-target" -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-musl.cmake" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$STAGE" \
        -DCMAKE_INSTALL_PREFIX="$STAGE" -DQT_HOST_PATH="$HOST" \
        -DBUILD_SHARED_LIBS=OFF -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF
    cmake --build "build/$module-target" --parallel "${JOBS:-2}"
    cmake --install "build/$module-target"
done
cmake -S desktop/quick-probe -B build/quick-probe -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-musl.cmake" \
    -DCMAKE_PREFIX_PATH="$STAGE" -DQT_HOST_PATH="$HOST" -DCMAKE_BUILD_TYPE=Release
cmake --build build/quick-probe --parallel "${JOBS:-2}"
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('archive', 'scripts/make-initramfs.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.static_elf('build/quick-probe/ominx-quick-probe')
PY
cp desktop/qt/quick.env build/provenance/qt-quick-source.env
cp build/sources/qtbase/src/3rdparty/wasm/DEJAVU-LICENSE build/provenance/
cp build/qtdeclarative-target/config.summary build/provenance/qt-quick-config.summary
"build/toolchain/bin/$TARGET-readelf" -l build/quick-probe/ominx-quick-probe > build/provenance/quick-probe-elf.txt
sha256sum build/quick-probe/ominx-quick-probe > build/provenance/quick-probe.sha256
