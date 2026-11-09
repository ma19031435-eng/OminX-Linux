#!/bin/sh
# Forge Studio (IDE for Forge apps) against the same musl Qt Quick prefix as the desktop shell.
# Output: build/forge-studio/forge-studio, which make initramfs packages as /bin/forge-studio.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
[ -f build/qt-prefix/lib/cmake/Qt6Quick/Qt6QuickConfig.cmake ] || {
    echo 'Build the source Qt Quick dependencies first (scripts/build-qt-quick-target.sh --dependencies-only)' >&2
    exit 1
}
cmake -S desktop/forge-studio -B build/forge-studio -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/build/qt-musl.cmake" \
    -DCMAKE_PREFIX_PATH="$ROOT/build/qt-prefix" -DCMAKE_BUILD_TYPE=Release \
    -DQT_HOST_PATH="$ROOT/build/qt-quick-host" \
    -DQT_HOST_PATH_CMAKE_DIR="$ROOT/build/qt-quick-host/lib/cmake" \
    -DQT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH="$ROOT/build/qtshadertools-host;$ROOT/build/qtdeclarative-host-full"
cmake --build build/forge-studio --parallel "${JOBS:-4}"
echo "Built build/forge-studio/forge-studio"
