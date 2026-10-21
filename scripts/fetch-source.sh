#!/bin/sh
# Checkout an exact source commit; all destinations must be disposable build paths.
set -eu
url=$1
ref=$2
commit=$3
dest=$4
if [ ! -d "$dest/.git" ]; then
    git clone --depth 1 --branch "$ref" "$url" "$dest"
fi
[ "$(git -C "$dest" rev-parse HEAD)" = "$commit" ] || {
    echo "Source mismatch at $dest (expected $commit); refusing to use it" >&2
    exit 1
}
[ -z "$(git -C "$dest" status --porcelain --untracked-files=no)" ] || {
    echo "Tracked source modified at $dest" >&2; exit 1;
}
