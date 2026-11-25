#!/bin/sh
# Builds the native Forge Studio bridge with a Qt 6 prefix and runs its runtime test
# against the host Forge test binary. Needs QT_PREFIX (headers, libs, moc).
#   QT_PREFIX=/path/to/qt  scripts/test-forge-studio-native.sh
# Optional: QT_INCLUDE, QT_LIBDIR, MOC override the layout. Output: build/host/forge-bridge-native-test.
# This checks the C++ bridge's logic and its process handling. It does not check the
# QML window, which is covered by tests/test_forge_studio.py.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
: "${QT_PREFIX:?set QT_PREFIX to a Qt 6.8 install (or set QT_INCLUDE, QT_LIBDIR and MOC)}"
QT_INCLUDE=${QT_INCLUDE:-$QT_PREFIX/include}
QT_LIBDIR=${QT_LIBDIR:-$QT_PREFIX/lib}
MOC=${MOC:-$QT_PREFIX/libexec/moc}
CXX=${CXX:-c++}
FORGE=$ROOT/build/host/ominx-forge-test
[ -x "$FORGE" ] || make build/host/ominx-forge-test

OUT=$ROOT/build/forge-studio-native
mkdir -p "$OUT"
HOST=$ROOT/desktop/forge-studio/host
"$MOC" "$HOST/forge_bridge.h" -o "$OUT/moc_forge_bridge.cpp"
# Qt 6 headers: one directory per module, plus the versioned private layout.
INC="-I$QT_INCLUDE"
for d in "$QT_INCLUDE"/*/ "$QT_INCLUDE"/QtCore/*/ "$QT_INCLUDE"/QtCore/*/QtCore/; do
    [ -d "$d" ] && INC="$INC -I$d"
done
$CXX -std=c++17 -Wall -Wextra -Werror -fPIC $INC -c "$HOST/forge_bridge.cpp" -o "$OUT/forge_bridge.o"
$CXX -std=c++17 -Wall -Wextra -Werror -fPIC $INC -c "$OUT/moc_forge_bridge.cpp" -o "$OUT/moc_forge_bridge.o"
$CXX -std=c++17 -Wall -Wextra -Werror -fPIC $INC -c "$HOST/test/bridge_native_test.cpp" -o "$OUT/bridge_native_test.o"
$CXX -o "$ROOT/build/host/forge-bridge-native-test" "$OUT/forge_bridge.o" "$OUT/moc_forge_bridge.o" \
    "$OUT/bridge_native_test.o" -L"$QT_LIBDIR" -Wl,-rpath,"$QT_LIBDIR" -lQt6Core

SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT
printf 'ID=ominx\n' > "$SCRATCH/os-release"
OMINX_FORGE_OS_RELEASE="$SCRATCH/os-release" "$ROOT/build/host/forge-bridge-native-test" "$FORGE" "$SCRATCH"
