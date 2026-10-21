#!/bin/sh
# Build upstream compiler, binutils and musl; no distribution target packages.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/toolchain/sources.env"
PREFIX="$ROOT/build/toolchain"
MCM="$ROOT/build/sources/musl-cross-make"
mkdir -p "$ROOT/build/sources"
if [ ! -d "$MCM/.git" ]; then
    git clone https://github.com/richfelker/musl-cross-make.git "$MCM"
fi
git -C "$MCM" checkout --detach "$MCM_COMMIT"
[ "$(git -C "$MCM" rev-parse HEAD)" = "$MCM_COMMIT" ]
cat > "$MCM/config.mak" <<CONFIG
TARGET = $TARGET
OUTPUT = $PREFIX
GCC_VER = $GCC_VERSION
BINUTILS_VER = $BINUTILS_VERSION
MUSL_VER = $MUSL_VERSION
LINUX_VER = $HEADERS_VERSION
GNU_SITE = https://ftp.gnu.org/gnu
COMMON_CONFIG += --disable-nls
GCC_CONFIG += --disable-libsanitizer --disable-libquadmath
CONFIG
make -C "$MCM" -j"${JOBS:-2}"
make -C "$MCM" install
"$PREFIX/bin/$TARGET-gcc" -dumpmachine | grep -qx "$TARGET"
# Preserve exact downloaded source hashes, recipe and licenses for audit/rebuild.
mkdir -p "$ROOT/build/provenance"
(cd "$MCM/sources" && sha256sum *) > "$ROOT/build/provenance/toolchain-sources.sha256"
cp "$MCM/config.mak" "$ROOT/build/provenance/toolchain-config.mak"
cp "$ROOT/toolchain/sources.env" "$ROOT/build/provenance/sources.env"
