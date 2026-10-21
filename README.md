# OminX — source-built x86-64 operating system

OminX is an independent Linux-based project. The new target is built from upstream
Linux, a source-built GCC/binutils/musl cross toolchain, a source-built Limine
bootloader, and original OminX init and console utilities. **No existing Linux
distribution, distribution root filesystem, package database, or host libc is used
as the new target's base.** The old Debian desktop build is preserved separately.

## Build from source

Use an x86-64 Linux build host with approximately 20 GB free disk space, internet
access and a C/C++ bootstrap compiler. The host distribution supplies build tools,
not target OS packages. On a Debian/Ubuntu **build host**, prerequisites are:

```sh
sudo apt-get install build-essential python3 git curl wget flex bison bc \
  libelf-dev libssl-dev autoconf automake libtool texinfo nasm mtools xorriso \
  qemu-system-x86 ovmf e2fsprogs dosfstools exfatprogs ntfs-3g
JOBS=4 make toolchain       # upstream GCC + binutils + musl, built into build/toolchain
JOBS=4 make build           # upstream Linux, original userspace, source bootloader, ISO
make target-check          # tests run against the actual musl-linked target executable
python3 scripts/test-sessions.py  # default unprivileged sessions
make boot-check            # recovery-mode firmware/storage regressions
python3 scripts/test-windows-filesystems.py  # FAT32/exFAT/NTFS read-only import tests
```

Exact upstream revisions and versions live in `toolchain/sources.env`. The pinned
musl-cross-make build recipe fetches and checks upstream source archive hashes;
Linux and Limine checkouts are validated against fixed commits. It is a toolchain
build utility, not a distribution. The build records source hashes, configuration,
compiler details and target libc identity under `build/provenance/`.

`make check` runs fast host-side tests in `build/host/`; it does **not** package host
libraries or replace target output. Target builds fail if the cross toolchain is
missing or its libc resolves outside `build/toolchain/`. Output is ignored by Git.

## Boot to the terminal

The build produces the normal `build/ominx-x86_64.iso` and the explicitly privileged
`build/ominx-recovery-x86_64.iso`, both with BIOS and x86-64 UEFI boot paths, plus
`bzImage`, `initramfs.cpio.gz`, and `SHA256SUMS`. Use the **normal ISO** by default.

```sh
(cd build && sha256sum -c SHA256SUMS)
make run
```

`make run` opens the VM display for its local keyboard terminal and exposes the
independent serial terminal on standard input/output. Firmware loads the actual
ISO bootloader; it does not bypass boot with QEMU's `-kernel` option.
Secure Boot must be disabled: these development images are not signed.

Normal boots automatically enter `ominx` (UID/GID 1000) at `ominx:/home/ominx$`:

```text
help
uname
cat /etc/os-release
write note Hello from OminX
cp note backup
cat backup
mv backup renamed
rm renamed
id
```

The default session has a private home/runtime directory, drops all saved root
identity and enables `no_new_privs`. Administrative mount commands are restricted to the explicitly selected recovery
menu entry. Power actions are delegated to the dedicated service. Normal-mode `control`, `reboot` and `poweroff` now use the bounded root power
broker; mount administration remains recovery-only.
[Session and device policy](docs/sessions.md).

Original commands also include `ls`, `pwd`, `cd`, `mkdir`, `echo`, `sync`, `exit`,
and `reboot`. `exit` restarts that console without exiting PID 1. Arguments support single/double quotes and backslash escapes; pipelines and shell
expansion are not implemented.
Absolute-path execution is supported for compatible executables added to the image.

### Original file-management backend

`files list PATH`, `files info PATH`, `files copy SOURCE DEST`, and `files move
SOURCE DEST` provide the new OminX Files backend. Copy and move refuse overwrites;
filenames with spaces and UTF-8 names work with quoting. JSON metadata is intended
for the future graphical frontend. `files remove --confirm FILE` is nonrecursive.
See [file operations and safety semantics](docs/files-and-storage.md).

In **root recovery mode**, read-only Windows-volume access is explicit: `attach DEVICE ro vfat`, `attach
DEVICE ro exfat`, or `attach DEVICE ro ntfs3`; then use `files` to inspect/import
files and `detach` when done. This does not run Windows programs.

### Optional persistent data

These administrative commands require **root recovery mode**. No disk is formatted
or mounted automatically. The root filesystem is RAM-backed;
explicitly attach an **already formatted ext4 data device** to persist files:

```text
attach /dev/vda
write /mnt/data/note This survives reboot
cat /mnt/data/note
detach
```

Choose the correct device for your VM; `/dev/vda` is an example, not an instruction
to modify an arbitrary disk. `attach DEVICE ro` mounts without journal replay and
refuses writes. Data mounts prohibit executable files, device nodes, and setuid.
A busy data mount prevents shutdown rather than silently forcing its removal.
This is not an installer; use disposable virtual data disks for development.

## Graphics/service work and login theme

The image now builds a narrow local power broker and additional kernel graphics
drivers. An original SDDM/Qt6 login theme is available under `desktop/sddm/ominx/`.
**The default image still has no Qt/KDE/SDDM runtime and does not yet boot to graphical
login.** Host theme rendering must not be confused with target authentication.
Optional development media now pass [source-built Qt Quick/theme guest checks](docs/validation/target-qt-quick.md),
with authentication explicitly disabled and no installed desktop session.
Optional [source-built shared graphics runtime](docs/validation/graphics-runtime.md) passes real
Mesa shader, Wayland, XKB and DRM checks in guests, and optional
[source-built desktop IPC services](docs/desktop-bus.md) also pass guest
authorization and supervision checks, alongside an isolated
[target Qt DBus integration test](docs/validation/target-qt-dbus.md). Neither is
password or desktop login.
See [implementation details, test boundaries and remaining integration](docs/graphics-login.md).

## Earlier verified session build

**19 automated checks, five normal-user configurations, five recovery regressions,
and all three Windows-filesystem cases passed.**
[Download the current images](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39468027444/artifacts/12285774394)
and review [the session validation report](docs/validation/sessions.md).
Use `ominx-x86_64.iso` for normal operation; `ominx-recovery-x86_64.iso` deliberately
starts root recovery. This remains automatic live login, not authenticated login.

## Earlier verified file/storage build

**17 target tests, five boot configurations, and FAT32/exFAT/NTFS read-only import
checks passed.** [Download the newer ISO](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39455615377/artifacts/12280299360)
and review [the recorded file/storage validation](docs/validation/files-and-storage.md).
The file-management layer is an original C backend with a console/JSON interface;
its graphical frontend and KDE integration are later steps.

## Original verified boot milestone

**Segment one passed all five x86-64 firmware/device cases and eight target tests.**
[Download the tested ISO and evidence](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39448085192/artifacts/12277394973)
or review the [successful run](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39448085192).

## Acceptance and scope

`scripts/test-platforms.py` tests real BIOS/UEFI ISO boot, USB-media boot, two QEMU
chipsets/CPU models, 256–1024 MiB RAM, PS/2 keyboard input into the local display
terminal, independent serial control, files, invalid-input handling, console
restart, virtio/SATA/NVMe data access, persistence across cold boots, read-only
mounts, reboot, shutdown and post-shutdown filesystem integrity. It saves serial
transcripts, framebuffer screenshots and machine-readable results.

[Recorded segment-one results and artifact instructions](docs/validation/segment-one.md).
Tests establish only the configurations actually run, not all physical PCs. The
initial x86 target is **x86-64**; a 32-bit-only i686 image is not included.

## Layout and next layers

```text
toolchain/                  Pinned upstream identities
boot/                       Independent bootloader configuration
src/core/                   Original init, console and data-mount operations
src/files/, src/lib/         Original file backend, safe copy/move and argument parser
scripts/build-toolchain.sh  Source cross-toolchain build
scripts/build-media.sh      Source bootloader and hybrid ISO creation
scripts/test-platforms.py   Firmware/media/terminal/storage acceptance matrix
tests/                      Host and target executable unit tests
config/, auto/              Preserved old desktop assets and Debian recipes
docs/legacy-debian.md        Historical desktop build documentation
```

The existing desktop is retained via `make legacy-build` and `make legacy-check`.
It remains a separate Debian-based track and is **not** the independent OS image.
KDE integration, original graphical applications/file manager, network services,
authentication, installation, updates and Windows-file workflows are later layers.
Normal mode is an unprivileged automatic live login, not authenticated login.
Root recovery remains explicitly selectable; use these images for isolated development.

## Licensing

This checkout retains its existing AGPLv3 license; it has not been relicensed.
Linux, musl, GCC, Limine and their dependencies retain upstream licenses. Original
proprietary components require confirmed ownership and compatible dependency use.
Source manifests are reproducibility aids, not a substitute for distribution
license obligations. See [architecture and boundaries](docs/source-os.md).
