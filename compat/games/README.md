# OminX game profiles

Each `<id>.game` file describes one title for the OminX game framework. Files
are installed to `/usr/share/ominx/games` (read-only in the image). The
console (`ominx-win game ...`) and the per-user daemon (`ominx-wined`) both
read them and enforce the same launch gate.

## Format

`key = value` lines, `#` comments. Unknown keys are errors, and the file name
must match `id`.

| key | meaning |
| --- | --- |
| `id` | `[a-z0-9-]{1,32}`, same as the file name |
| `name` | display name |
| `appid` | `[A-Za-z0-9_-]{1,32}`; names the Proton prefix |
| `runner` | `proton` (per-title prefix) or `wine` (default OminX prefix) |
| `dir` | install folder relative to `$HOME`, no `..` |
| `exe` | program relative to `dir`, no `..` |
| `anticheat` | `none`, `eac`, `battleye`, `vanguard`, `other` |
| `anticheat_status` | `none`, `vendor-opt-in`, `pending`, `denied` |
| `requires` | `none` or `eac-v2` (host must meet Epic's EAC Linux v2 requirements) |
| `notes` | short free text |

## Launch policy

* `anticheat = none` → `anticheat_status = none`. Launches when the runtime is ready.
* `anticheat_status = denied` → always refused. `vanguard` must be `denied`.
* `anticheat_status = pending` → refused until the publisher enables Linux.
* `anticheat_status = vendor-opt-in` → launches. If `requires = eac-v2`, the
  host must also pass the read-only checks in `src/lib/gamedb.c`
  (`ominx_host_eac_v2_missing`).

Profiles never add anti-cheat exemptions, spoofed hardware IDs, or driver
workarounds. A title is enabled only when its publisher says so.

## Game scheduling

When a title launches, the daemon moves the program into its own cgroup v2
group (`/sys/fs/cgroup/ominx/game-<appid>`) and sets the boost:

* CPU: `cpu.weight` 1000 (default 100).
* I/O: `io.weight` 800 (default 100).
* GPU: `power_dpm_force_performance_level` = `high` on amdgpu, restored to
  `auto` when the program exits. Other drivers are skipped.

Only `anticheat_status = vendor-opt-in` titles that pass the launch gate are
boosted. Titles with no anti-cheat run at default priorities. One title is
boosted at a time, because the GPU knob is global. Every knob is optional: a
missing or read-only knob is reported in the log and skipped, and the launch
still goes ahead. `ominx-win game info|check|launch` print the compatibility
and scheduling status before anything else.
