# OminX

**OminX** is an installable Debian 13 desktop image for 64-bit PCs, with original OminX branding and a familiar, taskbar-based Cinnamon desktop. The build recipe uses open components rather than Microsoft code or artwork.

This repository contains the **live-build recipe** and source assets, not a prebuilt ISO. Build it on a Debian-compatible amd64 machine to produce an installable live image.

## Desktop features and core apps

OminX uses Cinnamon to provide a familiar desktop layout: a bottom taskbar with a centered O Start button, pinned and grouped app icons, a searchable Start menu, system tray and clock on the right, right-side window controls, and common desktop icons. Original OminX blue/cyan shell styling is designed for people moving from Windows, while using Linux components and original artwork—not Microsoft code, Windows binaries, or copied Windows artwork. The desktop also provides workspaces, file search, notifications, settings, software installation and updates, networking, Bluetooth, printing/scanning, backups, firewall controls, accessibility tools, and remote desktop access.

Included applications cover everyday work and system care:

- **Software centers:** GNOME Software manages Debian packages and Flatpak apps; the Flathub catalog is configured. Synaptic is included as an advanced package manager.
- **Work:** Firefox ESR, LibreOffice, Thunderbird, PDF viewing, calculator, and file/archive tools.
- **Media and creativity:** VLC, GIMP, Inkscape, and standard image/audio utilities.
- **System:** Cinnamon settings, Nemo file manager, disks and partitions, system monitor, backup utility, firewall UI, remote desktop client, printer/scanner tools, and Orca screen reader.
- **Devices:** NetworkManager, Bluetooth, PipeWire audio, common Intel/AMD/Wi-Fi firmware, CPU microcode, Mesa/Vulkan, and firmware update support.

## Gaming and Windows app compatibility

Steam, Steam device rules, Valve Proton support, Wine 64/32-bit, Winetricks, Lutris, and 32-bit graphics/audio libraries are included in the ISO. Wine and the OminX `.exe`/`.msi` double-click handler are installed while building the image, so they are ready at first boot without downloading Wine then. OminX registers those files to open with **OminX Windows App Support**; its per-user Wine environment is initialized on first use. See `/usr/share/doc/ominx/compatibility.md` for details and compatibility limits. Protontricks is available through an optional first-use helper. The exact Proton runtime is downloaded by Steam after sign-in; it is not bundled in this image.

OminX is Linux, not Windows, and no compatibility layer can run every `.exe`. Windows kernel drivers, Windows Store/UWP apps, some DRM, and games whose anti-cheat blocks Linux generally will not work. Check a specific title on [ProtonDB](https://www.protondb.com/) or [Wine AppDB](https://appdb.winehq.org/) before relying on it. The welcome app and `/usr/share/doc/ominx/compatibility.md` explain setup and limitations.

## Memory optimization without pausing apps

OminX enables **zstd-compressed zram** for less-active memory pages. When RAM is under pressure, the kernel can compress pages into RAM and restore them on demand. It does not freeze, hibernate, close, or intentionally pause whole apps. This is page-level memory compression—not compression of installed app files—and it still uses CPU time. Very large workloads can remain slow or exhaust available memory. Details are in `/usr/share/doc/ominx/performance.md`.

## Per-game Game Mode

Feral GameMode is included. For a Steam game, add `/usr/games/gamemoderun %command%` to **Properties → General → Launch Options**. Lutris can enable GameMode per game. The tuning is requested only while a game uses it; supported systems may adjust performance policy and process scheduling. It cannot improve every bottleneck, and **OminX cannot promise latency will be cut in half**. Results depend on hardware, drivers, thermals, the game, display, and network. The OminX Game Mode Setup entry explains how to test it on your machine.

## Build the installable image

Build on a Debian 13 amd64 host with internet access, at least **8 GB RAM** and **40 GB free disk space**. Image size varies with Debian package updates.

```sh
sudo apt update
sudo apt install live-build debootstrap xorriso squashfs-tools dosfstools mtools \
  grub-pc-bin grub-efi-amd64-bin isolinux syslinux-common syslinux-utils \
  debian-archive-keyring
./build.sh
```

`build.sh` uses `sudo` when needed, configures the image via `auto/config`, runs `lb build`, then writes `SHA256SUMS`. The expected output is:

```text
live-image-amd64.hybrid.iso
SHA256SUMS
```

The build uses Debian Trixie repositories, including `contrib`, `non-free`, and `non-free-firmware`. It enables i386 multiarch, then installs Steam, Wine, and 32-bit Mesa/Vulkan/audio libraries. Flathub is added as an optional app source; apps from Flathub are not preinstalled. Internet access to Debian mirrors and Flathub is required. Run `make check` for static recipe and asset checks; a full ISO build needs the Linux build host above.

A GitHub Actions workflow automatically builds the installable ISO when this branch is updated. After a successful run, download the `OminX-installable-ISO-<commit>` artifact from the repository's **Actions** page; it contains the ISO and `SHA256SUMS` and is kept for 30 days. Local ISO building remains available with `./build.sh`.

### Test and install

1. Verify the image with `sha256sum -c SHA256SUMS`.
2. Test it in a UEFI or BIOS virtual machine before installing on real hardware. A VM with 4 GB RAM and a 30 GB virtual disk is a reasonable starting point.
3. Write the ISO to a USB drive using a disk-image writer. **Writing an image erases the selected USB drive.**
4. Boot the live session and choose the **Install** entry in the boot menu.

Back up important files before installation. Hardware support, proprietary graphics drivers, and Secure Boot behavior vary by machine. The image includes open-source graphics drivers and common (including non-free) firmware, but not every vendor driver.

## Repository layout

```text
auto/config                         Reproducible live-build configuration
build.sh                            Root-aware ISO build entry point
config/package-lists/               Desktop package selection
config/hooks/normal/                Multiarch, Steam, Wine, and Flathub setup
config/includes.chroot/             OminX branding, defaults, apps, and documentation
scripts/check-config.sh             Static sanity checks
```

To change packages, edit `config/package-lists/ominx.list.chroot`. Build options live in `auto/config`. Build outputs and ISO artifacts are ignored by Git.

## Licensing and third-party software

The OminX project files and original artwork in this repository are covered by the repository's **GNU AGPLv3** license. The image combines Debian packages and third-party software that retain their own licenses and trademarks. Steam is proprietary software from Valve; non-free firmware is subject to its respective terms. OminX is an independent project and is not affiliated with or endorsed by Microsoft, Valve, or Debian.
