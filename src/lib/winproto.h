#ifndef OMINX_WINPROTO_H
#define OMINX_WINPROTO_H
/* Fixed layout for the OminX Windows compatibility services. Nothing here is
   user-configurable on the target: the root setup service, per-user daemon,
   console client and desktop shell must all agree on these paths.
   See docs/windows-compatibility.md for the lifecycle and threat model. */

/* Source-built glibc/Wine runtime prefix, packaged read-only in the image.
   Its layout is audited by scripts/stage-wine-runtime.py:
   VERSION (one line), bin/wine (+wineserver), lib/ld-linux-x86-64.so.2,
   lib/wine/..., share/wine/... and optionally share/dxvk/{x64,x32}/,
   share/vkd3d-proton/{x64,x86}/ DLL sets. */
#define OMINX_WINE_RUNTIME "/usr/lib/ominx/wine-runtime"
#define OMINX_WINE_LOADER "lib/ld-linux-x86-64.so.2"

/* Root first-install/first-boot service (never executes Windows code). */
#define OMINX_WINSETUP_SOCKET "/run/ominx/winsetup.sock"
#define OMINX_WINE_STATE_DIR "/var/lib/ominx/wine"
#define OMINX_WINE_SYSTEM_MARKER "/var/lib/ominx/wine/system-setup-v1"
#define OMINX_WINE_RUNTIME_REPORT "/run/ominx/wine-runtime.conf"
/* Written verbatim to /proc/sys/fs/binfmt_misc/register by the root service
   so ./program.exe reaches the same validated path as the file manager.
   /bin/ominx-win-binfmt is ominx-win invoked under a reserved argv[0]. */
#define OMINX_WINE_BINFMT_NAME "OminXWine"
#define OMINX_WINE_BINFMT_LINE ":OminXWine:M::MZ::/bin/ominx-win-binfmt:"
/* Proton-era games allocate many memory areas; Wine also wants a high value. */
#define OMINX_WINE_MIN_MAP_COUNT 1048576

/* Per-user daemon. Socket lives in XDG_RUNTIME_DIR; the environment variable
   is set by the session layer for the console and the desktop shell. */
#define OMINX_WINED_SOCKET_NAME "ominx-wined.sock"
#define OMINX_WINED_SOCKET_ENV "OMINX_WINED_SOCKET"
/* Relative to HOME. ~/.wine is kept as a compatibility symlink to the first. */
#define OMINX_WINE_PREFIX_REL ".local/share/ominx/wine/prefix"
#define OMINX_PROTON_REL ".local/share/ominx/proton/compatdata"
#define OMINX_WINE_LOG_REL ".local/share/ominx/wine/logs/last-run.log"
#define OMINX_WINE_MARKER ".ominx-setup-v1"

#define OMINX_WIN_MAX_REQUEST 8192
#define OMINX_WIN_MAX_ARGS 8
#define OMINX_WIN_MAX_ARG 512
#define OMINX_WIN_MAX_APPS 64
#define OMINX_WIN_MAX_RUNNING 8
#define OMINX_WIN_SETUP_VERSION "1"
#endif
