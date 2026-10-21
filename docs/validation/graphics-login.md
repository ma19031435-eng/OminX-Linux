# Graphics / controlled-power acceptance

## Accepted source image

- Commit: `35514119f11e775ab696d6c3c67be5c221366848`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39482457386
- Conclusion: **success**.
- Artifact: `12292123653`, `OminX-x86-35514119f11e775ab696d6c3c67be5c221366848`, 57,908,167 bytes.
- 29 target userspace tests; five normal-user configurations; five recovery
  configurations; FAT32/exFAT/NTFS read-only cases; three native framebuffer cases.
- Bochs/BIOS, virtio/UEFI and QXL/BIOS passed native framebuffer-name, device
  permissions, displayed console/keyboard and controlled-power checks.
- Normal-user tests exercise actual broker-mediated reboot, return to UID 1000
  after reboot, and broker-mediated poweroff. Host broker tests also cover packet
  bounds, injection rejection, idle clients and singleton behavior.

The earlier graphics failures were real failures, not accepted results. Initial
assertions had incorrect upstream framebuffer names. After those corrections,
the guest exposed a second issue: `/proc/fb` was absent because `CONFIG_FB_DEVICE`
was not enabled. The accepted build explicitly enables that interface and checks
all required built-in graphics configuration values **after** `olddefconfig`.

Evidence excerpts are in `graphics-login/`; full guest logs, screenshots, kernel
configuration, source provenance and ISO images are in the workflow artifact.
These are finite virtual-device checks, not physical GPU certification or 3D tests.

## Login theme — separate host validation

- Theme commit: `129af49a9194cb68c44055c378bce3955c9e9904`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39473373846
- Artifact: `12288086419`, 478,341 bytes.
- Qt 6 mock-context interaction/layout tests and pinned upstream SDDM 0.21 host
  test-mode rendering passed. The preview is in `graphics-login/login-preview.png`.

**This does not establish successful target authentication, SDDM startup or Plasma
session launch.** The accepted default source image still starts its automatic
live console. Subsequent target Qt raster acceptance is documented separately in
[target-qt.md](target-qt.md); it is not an authenticated login test either.
