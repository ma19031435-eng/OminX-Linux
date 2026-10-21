#!/bin/sh
# Build-host validation ONLY. Not a target install or permission to copy host libs.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. desktop/sddm/source.env
mkdir -p build/sources
scripts/fetch-source.sh https://github.com/sddm/sddm.git "$SDDM_TAG" "$SDDM_COMMIT" "$ROOT/build/sources/sddm"
cmake -S build/sources/sddm -B build/sddm-host -DBUILD_WITH_QT6=ON \
    -DNO_SYSTEMD=ON -DENABLE_JOURNALD=OFF -DBUILD_MAN_PAGES=OFF
cmake --build build/sddm-host --target sddm-greeter-qt6 -j"${JOBS:-2}"
