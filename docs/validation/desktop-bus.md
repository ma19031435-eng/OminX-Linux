# Source-built desktop bus acceptance

- Commit: `bdb5c9866bdffa3b2dd51805e219b5af0cf91d3a`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39562172882
- Conclusion: **success**.
- Artifact: `12328765920`, `OminX-desktop-bus-development-bdb5c9866bdffa3b2dd51805e219b5af0cf91d3a`, 10,194,455 bytes.
- Kernel: SHA256-verified source artifact from accepted commit
  `35514119f11e775ab696d6c3c67be5c221366848`, run `39482457386`.
- Original userspace and bus components were rebuilt from this run's checkout.
- **38 target userspace/packaging/source-safety checks passed.**

## Actual media results

| Case | Firmware/mode | Observed |
| --- | --- | --- |
| bus-bios | BIOS, normal UID 1000 | EXTERNAL peer authentication, protected-name refusal, system peer-message refusal, session roundtrip, daemon restart, immutable machine identity, controlled shutdown |
| bus-uefi | UEFI, normal UID 1000 | Same checks |
| bus-isolation | BIOS, explicit root recovery | UID 1001 denied on both buses, singleton protection, supervisor killed and restarted by PID 1, old daemon replaced, repeated UID 1000 roundtrip/restart checks, controlled shutdown |

The tests inspect actual `/proc/PID/status` values for the running bus daemons:
UID/GID 81 or 1000 in every credential slot, empty supplementary groups, zero
permitted/effective/inheritable/ambient capabilities and no-new-privileges enabled.
UID 1000 cannot signal the system daemon. It can stop its own session daemon,
and the original supervisor restarts it. Killing the root supervisor in the
isolated recovery guest tests PID 1 recovery and parent-death child cleanup.

The cross-UID test first establishes that the system daemon is live, closes the
root connection before dropping to UID 1001, and verifies the same live daemon
after the denial checks. It does not hand the unprivileged child an authenticated
root connection or accept a missing daemon as proof of authorization refusal.

Result JSON and bounded guest/log excerpts are retained in `desktop-bus/`.
The artifact contains the complete files and pinned upstream source/license
material. The early unprivileged test failed because `/proc/1/exe` is correctly
unreadable across UIDs; the revised source-boot guard uses the root bootstrap
lock and read-accessible image/process identity instead. Earlier failed runs
are not acceptance evidence.

## Default-image regression

The full source core run at the same accepted commit also succeeded:
https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39562172951
It passed 38 userspace checks, five normal-session cases, five recovery/platform
cases, read-only VFAT/exFAT/NTFS3 cases and bochs/virtio/qxl graphics cases.
This checks that adding the optional supervisor did not make the default image
depend on the optional bus bundle.

## Scope

This is actual source-linked IPC and supervised service behavior inside the
independent image, not a host D-Bus test. The feature remains optional during
packaging. It is **not** password authentication, Qt DBus integration, seat
management, an upstream SDDM daemon or a KDE Plasma session. The graphical-login
request remains unfinished. See [the implementation boundary](../desktop-bus.md).
