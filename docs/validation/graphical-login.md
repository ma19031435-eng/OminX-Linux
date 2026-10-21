# Graphical login acceptance

- Commit: `8cf2b2d595bf3f32a168d12b3a4605f36c6d67f7`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39601728439
- Conclusion: **success**.
- Artifact: `12346811537`, `OminX-graphical-login-8cf2b2d595bf3f32a168d12b3a4605f36c6d67f7`,
  20,527,975 bytes.
- Target/host suite in the same job: **67 checks passed**.
- Kernel: the accepted source kernel from run `39564535782` (commit
  `29ee23893c055263aa46fb68e701102d9005eb44`), re-verified by SHA256 before use.
- Qt: the source-built static Qt 6.8.3 / Qt Quick prefix used by the accepted
  [Qt Quick guest checks](target-qt-quick.md); no host Qt is copied into the image.

## Guest results

| Case | Firmware / display | Result |
| --- | --- | --- |
| `login-bios` | BIOS, Bochs std framebuffer | PASS |
| `login-uefi` | UEFI (OVMF), virtio-gpu | PASS |
| `login-recovery` | BIOS, explicit root recovery | PASS |

```
PASS login-bios: themed greeter, refused password, greeter-only authorization, authenticated session, logout, login-screen poweroff
PASS login-uefi: themed greeter, refused password, greeter-only authorization, authenticated session, logout, login-screen poweroff
PASS login-recovery: explicit root console, musl crypt verification, password change, no account creation
```

## What is original here

| Component | Path | Role |
| --- | --- | --- |
| `ominx-login` | `src/login/broker.c` | root authentication broker |
| `ominx-seat` | `src/login/seat.c` | greeter/session display supervisor |
| `ominx-desktop` | `desktop/desktop-shell/` | Qt Quick login screen and desktop session |
| `ominx-passwd` | `src/login/passwd.c` | recovery password change |
| `ominx-login-probe` | `src/login/probe.c` | authorization diagnostic |
| account hashing | `scripts/ominx-hash.py` | build-time sha512crypt seeding |

No PAM, no SDDM daemon, no X11/Wayland server and no distribution login stack is
used. Password verification is musl's `crypt(3)` against sha512crypt records in a
root-only file; the greeter never sees another account's credentials and never
starts a session itself.

## Observed guest behaviour

Actual lines from `login-bios` (full transcripts in this directory):

```
seat: ready greeter-uid=1001 session=/bin/ominx-desktop
seat: greeter started pid=75
greeter: listed 1 unlocked accounts
OMINX_GREETER_READY
OMINX_LOGIN_DENIED user=ominx reason=credentials
login: service ready accounts-file=/etc/ominx/accounts
login: denied name=ominx reason=credentials attempts=1
```

The tests then proved, in the same booted image:

1. The themed login screen really rendered: the accent colour `#74e0c7` covered
   more than 2000 framebuffer pixels and no session pixel was present.
2. A wrong password was refused by the broker and started no session.
3. The signed-in user identity (UID 1000) **cannot even connect** to the login
   socket: it is `root:greeter` mode 0660, so the kernel returns
   `connect: Permission denied` for `AUTH`, `SESSION` and `LIST`. Running
   `/sbin/ominx-login --check` as that user is refused because it is not the
   root source-boot context.
4. The correct password started a real session: `session started uid=1000` and
   `OMINX_SESSION_READY user=ominx home=/home/ominx`, with the desktop taskbar
   colour `#0b1520` covering more than 20000 pixels and the greeter gone.
5. Logging out from the session ended it (`session ended uid=1000`) and returned
   to a freshly rendered login screen.
6. The keyboard power action on the login screen shut the machine down through
   the greeter → broker → seat → power broker chain; nothing else in that guest
   can request power.
7. Recovery kept the explicit unauthenticated root console, listed the packaged
   accounts, verified the shipped hash with musl `crypt`, changed the password,
   proved the new password verifies and the old one no longer does, and refused
   to create an account or to touch `root`.

## Authorization model

- The broker socket is reachable only by root and the `greeter` account (UID/GID
  1001). `LIST`/`AUTH`/`POWER` are for the greeter; `SESSION`/`POWERSTATE`/`STATUS`
  are root-only; everything else is refused and logged.
- A successful authentication yields exactly one pending session, consumed by the
  seat and expiring after 60 seconds (2 seconds in the host-test build).
- Three failures start a bounded backoff that applies to any attempted name, so
  the lockout itself does not disclose which accounts exist. Unknown names still
  run a full sha512crypt pass against a fixed dummy hash.
- The seat runs the session program as the authenticated UID with
  `NO_NEW_PRIVS`, `PDEATHSIG`, cleared environment and only the video/input/render
  groups. The greeter runs as UID 1001 and cannot read `/home/ominx`.
- Account records are fixed by the image: `/etc/ominx/accounts` is root-owned
  mode 0400, its grammar is enforced identically by the packaging script and the
  C parser, and the session shell is a fixed path.

## Host-side checks

`tests/ui/test_desktop_shell.py` loads both QML surfaces with host Qt 6 before the
expensive target build and verifies the masked password field, the remembered
username, the keyboard power action, start-menu focus on Log out, Enter
activation, the session power action and the session-information panel.
`tests/test_login.py` runs the broker itself (target build under `make
target-check`) for listing, acceptance, refusal, lockout, stale-session expiry,
power recording, unsafe account files, duplicate-instance refusal and
password-free logs. `tests/test_desktop_login.py` covers packaging rules.

## Not established

This is a framebuffer login and session, not a Wayland/X11 compositor session:
there is no window stacking, no multi-window compositor, no KDE Plasma
components, no seat/VT handoff beyond the single console, and no hardware GL.
Password storage is a live-image demo credential that recovery can change; there
is no account creation, no password expiry and no remote authentication.
