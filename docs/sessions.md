# Unprivileged live sessions and desktop device access

The default source-built image now starts both the display and serial consoles as
**`ominx`, UID/GID 1000**, not root. This is automatic login for an isolated live
development environment, **not password authentication or a production login
manager**. The old Debian build remains a separate track.

## Session setup

PID 1 remains root to supervise consoles and manage device ownership. Each console
child acquires its controlling terminal, assigns it to the intended account, and
then performs session setup before accepting any input:

- Clears inherited environment variables; establishes `HOME`, `USER`, `LOGNAME`,
  `PATH`, `SHELL`, `LANG`, `TERM` and a private `XDG_RUNTIME_DIR`.
- Replaces supplementary groups with the explicit single-seat device groups.
- Sets **real, effective and saved** GID/UID to 1000, checking all results.
- Enables Linux `no_new_privs`, inherited by executed programs.
- Uses a private umask of 077 and changes to `/home/ominx`.
- Fails closed if any step fails: it does not open a root fallback console.

`/home/ominx` and `/run/user/1000` are owned by UID/GID 1000 with mode 0700.
`/root` is root-only 0700. The image includes original minimal passwd/group/shadow
records; password fields are locked. Those records describe identities but are
not used to authenticate this automatic live login.

Run `id` at the console to inspect real/effective/saved identities, groups,
`no_new_privs`, home and runtime directory. Normal prompts end in `$`; recovery
prompts end in `#`. Executed applications and restarted consoles retain the normal
account's permission boundary. Both consoles intentionally belong to the same
single live account; they are not isolated from one another.

## Device policy for the future desktop

An original, small policy in PID 1 assigns recognized **character** device nodes:

| Device names | Group | Mode |
|---|---|---|
| `/dev/dri/cardN`, `/dev/fbN` | video (44) | 0660 |
| `/dev/dri/renderDN` | render (107) | 0660 |
| `/dev/input/eventN` | input (104) | 0660 |

The live account receives those three supplementary groups. Consoles are assigned
to that account with mode 0600. Block devices, `/dev/mem`, arbitrary device names,
and symlink entries are not granted access. The policy scans at startup and during
PID 1's child-reaping loop to accommodate later-created nodes. `/dev` is trusted,
root-owned kernel-managed state; this code is not a hostile-filesystem sandbox.

This is a **single-seat development policy**. Input-group access permits capturing
that seat's input; it is inappropriate for mutually distrusting users or multiple
seats. There is not yet a compositor, seat arbitration, DRM-master handoff or a
logind/seatd-compatible service. Permission setup is a prerequisite for that stack,
not evidence that KDE or hardware-accelerated rendering is running. The acceptance
test exercises the available QEMU card/input nodes; a render node is only managed
when a driver actually exposes one.

## Explicit root recovery

The normal ISO's second menu entry is clearly labelled **root recovery, no
authentication**. It adds the exact kernel token `ominx.recovery=1`. The default
entry does not. A separate `ominx-recovery-x86_64.iso` is built for deliberate
administration and root regression tests, with entry two preselected.

In default sessions:

- Filesystem permissions prevent changing `/etc`, reading `/etc/shadow`, entering
  `/root`, or directly opening raw data disks.
- `attach`, `detach`, `reboot` and `poweroff` refuse administrative actions.
- There is no `sudo`, setuid helper, password bypass or hidden root command.

Choose the recovery menu entry for existing data-mount/import and power-control
workflows. Until a narrow privileged service is implemented, normal users must
stop a VM through its host controls instead of a guest `poweroff` command. Do not
use the recovery ISO as the normal default. Users who can change boot choices
can intentionally obtain root; this is not physical-access protection, Secure
Boot, an authenticated install or a hardened multi-user appliance.

## Tests and next gate

`python3 scripts/test-sessions.py` boots the **normal ISO** on all five existing
firmware/device configurations. It checks IDs and saved IDs, zero permitted,
effective and ambient capabilities, `no_new_privs`, runtime/home ownership,
private file modes, denied system-file/raw-disk access, refused admin commands,
card/input permissions, local keyboard operation, program execution and respawn.
It exits those VMs using QMP, not an in-guest root escape. The existing storage,
shutdown and Windows-filesystem tests now boot the **explicit recovery ISO**.

The next gate is a narrowly scoped privileged control/seat service and the
source-built graphics/input libraries, followed by Qt/KDE and the graphical file
manager. Authentication, multiple users, persistent home directories and desktop
session switching remain separate work. The [recorded validation](validation/sessions.md) passed all five default-session
cases, five recovery regressions, all three Windows-filesystem checks and the
19-check automated suite.
