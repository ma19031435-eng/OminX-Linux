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
  qemu-system-x86 ovmf e2fsprogs
JOBS=4 make toolchain       # upstream GCC + binutils + musl, built into build/toolchain
JOBS=4 make build           # upstream Linux, original userspace, source bootloader, ISO
make target-check          # tests run against the actual musl-linked target executable
make boot-check            # boots actual media through BIOS and UEFI firmware
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

The build produces `build/ominx-x86_64.iso`, with BIOS and x86-64 UEFI boot paths,
plus `bzImage`, `initramfs.cpio.gz`, and `SHA256SUMS`.

```sh
(cd build && sha256sum -c SHA256SUMS)
make run
```

`make run` opens the VM display for its local keyboard terminal and exposes the
independent serial terminal on standard input/output. Firmware loads the actual
ISO bootloader; it does not bypass boot with QEMU's `-kernel` option.
Secure Boot must be disabled: these development images are not signed.

At `ominx:/root#`:

```text
help
uname
cat /etc/os-release
write note Hello from OminX
cp note backup
cat backup
mv backup renamed
rm renamed
poweroff
```

Original commands also include `ls`, `pwd`, `cd`, `mkdir`, `echo`, `sync`, `exit`,
and `reboot`. `exit` restarts that console without exiting PID 1. Arguments are
whitespace-separated; quoting, pipelines and shell expansion are not implemented.
Absolute-path execution is supported for compatible executables added to the image.

### Optional persistent data

No disk is formatted or mounted automatically. The root filesystem is RAM-backed;
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
src/core/                   Original init, console, file and data-mount operations
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
The new console has no login security; use it for isolated development.

## Licensing

This checkout retains its existing AGPLv3 license; it has not been relicensed.
Linux, musl, GCC, Limine and their dependencies retain upstream licenses. Original
proprietary components require confirmed ownership and compatible dependency use.
Source manifests are reproducibility aids, not a substitute for distribution
license obligations. See [architecture and boundaries](docs/source-os.md).
