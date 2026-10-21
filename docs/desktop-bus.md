# Source-built desktop IPC services

This dependency stage has passed real guest authorization and lifecycle tests.
See [the validation report](validation/desktop-bus.md). It does **not** complete
SDDM, PAM/password authentication, a seat manager, Qt DBus integration or Plasma.

## Source boundary

`scripts/build-desktop-bus.sh` builds upstream Expat 2.7.1 and D-Bus 1.16.2 with
the dedicated source-built GCC/musl toolchain, then builds the original OminX
supervisor and guest probe. The three packaged executables must be static x86-64
ELF files without an interpreter. Target pkg-config lookup is restricted to the
source-built prefix; no host libdbus or distribution target package is copied.

Expat is pinned by upstream Git commit. D-Bus comes from its official freedesktop
source release URL and is checked against a pinned SHA256. The checksum was
corroborated against the public release checksum record at
https://github.com/buildroot/buildroot/blob/master/package/dbus/dbus.hash — only
the source checksum was used, not that project's target packages, root filesystem,
init scripts or build machinery. The OminX recipes and packaging are independent.

The archive fetcher rejects traversal, multiple source roots, duplicate members,
links, special files and excessive extracted sizes. Reusing an extracted tree
compares its files and modes against the checksum-verified archive again; missing,
changed or injected source files are rejected. Builds are out-of-tree.

The development artifact includes upstream source archives, source identities,
compiler/build configuration, hashes, licenses and test evidence. The optional
image includes the upstream license texts. Original components retain this
repository's license; no new proprietary license or release-compliance claim is
made for upstream components.

## Fixed supervision and privilege separation

With `--bus-dir build/desktop-bus`, packaging adds:

- `/sbin/dbus-daemon` from the upstream source build.
- `/sbin/ominx-desktop-bus`, the original root supervisor.
- `/bin/ominx-bus-probe`, an explicit development-only acceptance executable.
- A locked `messagebus` account (UID/GID 81), original bus policies and licenses.

Without the option the standard image remains unchanged: no bus daemon/account
is packaged, and PID 1 does not launch the optional service.

PID 1 supervises the fixed supervisor, which supervises exactly two fixed daemon
commands. It exposes no arbitrary executable/argument API. The supervisor takes
a singleton root-only lock under `/run/ominx`; children close that descriptor on
exec. Restart attempts are rate-limited. Children receive `SIGKILL` if their
supervisor dies unexpectedly, preventing orphan listeners from surviving a
supervisor replacement. Normal supervisor termination requests graceful child
shutdown before a bounded forced cleanup.

Before exec the supervisor clears the environment and supplementary groups,
sets all real/effective/saved UID/GID slots, and enables `no_new_privs`. The system
bus runs as UID/GID 81, not root. The session bus runs as UID/GID 1000. Guest tests
check all four kernel UID/GID values, empty supplementary groups, zero effective,
permitted, inheritable and ambient capabilities, and `NoNewPrivs: 1`.

The root supervisor verifies actual source PID 1 through `/proc/1/exe` before
changing anything. The unprivileged probe cannot read that root symlink under
Linux's credential checks; it instead checks the init comm, OminX image identity
and protected root bootstrap lock before touching a bus. The explicit test modes
must not be run against an ordinary build-host bus.

## IPC policy

Both listeners are local filesystem Unix sockets and advertise **EXTERNAL**
authentication only. This means kernel UID-based IPC authentication, not password
login or authorization of a person at a graphical seat. No TCP listener, anonymous
authentication, service activation directories or setuid activation helper is
packaged/enabled.

System socket: `/run/dbus/system_bus_socket`.

- Only root and the live account UID 1000 may connect.
- Only root may own system service names.
- The live account may call the D-Bus driver interface for discovery/credentials,
  but cannot own privileged names or send arbitrary peer messages.
- There is no new root command, mount, service-management or power API over D-Bus.
  Power requests still use the independently checked original Unix power broker.

Session socket: `/run/user/1000/bus`.

- The enclosing user runtime directory remains mode 0700.
- The live UID owns its session names and may exchange session messages.
- This is a single-user session policy, not isolation between applications of the
  same UID. Root is not an adversary that a user-owned bus can exclude.

Normal consoles receive the explicit system/session bus addresses when the
optional service is present. Startup is asynchronous; the probe waits for
readiness. A future graphical startup path must gate session launch on actual
service readiness, not just on a socket filename existing.

## Machine identity

The supervisor obtains random bytes with `getrandom`, writes a fresh 32-hex machine
identity once per RAM boot, and makes `/etc/machine-id` root-owned and read-only.
`/var/lib/dbus/machine-id` is a fixed symlink to that file. No fixed identity is
baked into the archive. Supervisor restarts validate/reuse the existing identity;
invalid files fail closed. This is not a persistent installed-machine identity.

## Reproduction

```sh
make toolchain
MESON=/path/to/meson JOBS=4 scripts/build-desktop-bus.sh
make build
python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz \
  build/ominx-files build/ominx-control --bus-dir build/desktop-bus
make media
python3 scripts/test-desktop-bus.py
```

The CI workflow installs pinned Meson as a **host tool**, reuses a verified
source-built kernel artifact, rebuilds current original userspace and authors
new BIOS/UEFI media. It does not use a host kernel or an existing distro base.

Before desktop integration, the system policy must be deliberately extended for
real greeter/seat accounts and narrowly allowed interfaces, and target Qt DBus,
authentication, compositor and Plasma services must be built and tested. Do not
replace these gates with a permissive system policy or fabricated session model.
