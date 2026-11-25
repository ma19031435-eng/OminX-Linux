#!/bin/sh
# C compiler for static x86-64 musl binaries when the source-built GNU toolchain
# (scripts/build-toolchain.sh) cannot be built. It runs Zig's bundled clang and
# musl libc, pinned to the ziglang wheel in ZIG_PYTHON's environment.
# Use: make <target> CC="$PWD/scripts/musl-cc-zig.sh"
# The shipped path stays build/toolchain/bin/x86_64-linux-musl-gcc.
set -eu
PY=${ZIG_PYTHON:-python3}
exec "$PY" -m ziglang cc -target x86_64-linux-musl "$@"
