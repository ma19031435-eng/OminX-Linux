# OminX

**OminX** is an installable Debian 13 desktop image for 64-bit PCs, with an original visual identity and a purpose-built Cinnamon desktop. OminX Aurora is not a Windows theme: it pairs deep midnight surfaces, sea-glass highlights, luminous sky blue, and restrained violet with original OminX artwork and Linux components.

This repository contains the **live-build recipe** and source assets, not a prebuilt ISO. Build it on a Debian-compatible amd64 machine to produce an installable live image.

## Desktop features and core apps

The shell is composed around a slim command bar at the top: the OminX Launcher and workspace overview sit at the left, grouped running apps occupy the center, and system indicators and the clock sit at the right. The Launcher opens a custom OminX surface with pinned apps, recommendations, responsive search, an all-apps view, and session power options. Its application index is deferred until needed; searches are debounced and large result lists are paged in small batches. Store and Settings use screen-aware sizing and debounced search. Across the shell and GTK apps, OminX Aurora uses layered dark surfaces, crisp borders, sea-glass accents, subtle blue-violet light, and custom OminX artwork. The desktop also provides workspaces, file search, notifications, settings, software installation and updates, networking, Bluetooth, printing/scanning, backups, firewall controls, accessibility tools, and remote desktop access.

Nemo (Files) uses its native navigation model: double-click to open, a details/list view sorted by name with folders first, a Places sidebar for Home and common folders, mounted devices and network locations, breadcrumb navigation, search, a new-folder action, and a status bar. Home, Computer, Trash, mounted volumes, and Network icons are enabled on the desktop.

**OminX Store** is an original storefront with a navigation rail, search, app/game categories, featured app cards, Library, and Updates. It highlights included software and forwards catalog searches, installed-app management, and updates to GNOME Software's Debian and Flatpak backends—so package operations are real, not a mock catalog. **OminX Settings** uses the Aurora design system to organize native tools into Workspace, Devices, Connectivity, Appearance, Applications, Accounts, Time & input, Gaming, Accessibility, Privacy & security, and Updates. **OminX Setup** guides new users through connection status, software and browser preferences, and gaming tools; each step is optional, settings can be revisited later, and optional software is never installed without a user action.

Common keyboard workflows are included: **Super+E** opens Files, **Super+R** opens the Run dialog, **Super+I** opens OminX Settings, **Ctrl+Shift+Esc** opens System Monitor, **Super+D** shows the desktop, **Super+L** locks the session, **Super+Tab** opens the window overview, **Super+Left/Right** tiles a window, **Super+Up/Down** maximizes or restores it, and **Super+Shift+S** selects an area for a screenshot. Super is usually the Windows-logo key on PC keyboards. Shortcuts are provided by Cinnamon and can be changed in Keyboard settings.

OminX keeps useful Linux workflows while giving the shell, launcher, artwork, and app hubs their own visual language. It does not copy Microsoft code, protected artwork, or Windows binaries.

Included applications cover everyday work and system care:

- **Software centers:** OminX Store provides the discovery home and forwards full-catalog searches, installed-app views, updates, and source management to GNOME Software. Debian package and Flatpak installation remain handled by the standard backend; Flathub is configured. Synaptic is included as an advanced package manager.
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
sudo apt install python3 live-build debootstrap xorriso squashfs-tools dosfstools mtools \
  grub-pc-bin grub-efi-amd64-bin isolinux syslinux-common syslinux-utils \
  debian-archive-keyring
./build.sh
```

`build.sh` uses `sudo` when needed, generates original OminX Aurora splash art, configures the image via `auto/config`, runs `lb build`, verifies the generated GRUB menu and both graphical/text Debian Installer payloads, then writes `SHA256SUMS`. If an ISOLINUX loader is enabled by a future build configuration, its OminX menu is validated too. The custom GRUB menu is authored to offer a live session, graphical install, and safe/advanced modes; the build fails rather than publishing if the menu or installer payloads are missing. The expected output is:

```text
live-image-amd64.hybrid.iso
SHA256SUMS
```

The build uses Debian Trixie repositories, including `contrib`, `non-free`, and `non-free-firmware`. It enables i386 multiarch, then installs Steam, Wine, and 32-bit Mesa/Vulkan/audio libraries. Flathub is added as an optional app source; apps from Flathub are not preinstalled. Internet access to Debian mirrors and Flathub is required. Run `make check` for static recipe, setup-wizard, splash-image, and boot-menu source checks. The GitHub Actions ISO workflow also launches OminX Store, Settings, Welcome, and Setup under Xvfb in a Debian 13 GTK environment, exercising their search/navigation and first-run views plus their installed shell launchers before building the image; it validates the generated GRUB menu, any active ISOLINUX menu, and installer files before publishing. A full local ISO build needs the Linux build host above.

A GitHub Actions workflow automatically builds the installable ISO when this branch is updated. After a successful run, download the `OminX-installable-ISO-<commit>` artifact from the repository's **Actions** page; it contains the ISO and `SHA256SUMS` and is kept for 30 days. The ISO also contains `/usr/share/doc/ominx/build-info.txt` with its exact source commit, workflow run ID, and UTC build time, so you can verify which revision is installed. Local ISO building remains available with `./build.sh`.

### Test and install

1. Verify the image with `sha256sum -c SHA256SUMS`.
2. Test it in a UEFI or BIOS virtual machine before installing on real hardware. A VM with 4 GB RAM and a 30 GB virtual disk is a reasonable starting point.
3. Write the ISO to a USB drive using a disk-image writer. **Writing an image erases the selected USB drive.**
4. On a verified refreshed ISO, choose **Try OminX Aurora** to use the live desktop or **Install OminX (graphical)** to start Debian Installer.

Back up important files before installation. Hardware support, proprietary graphics drivers, and Secure Boot behavior vary by machine. The image includes open-source graphics drivers and common (including non-free) firmware, but not every vendor driver.

## Repository layout

```text
auto/config                         Reproducible live-build configuration
build.sh                            Root-aware ISO build entry point
config/package-lists/               Desktop package selection
config/bootloaders/                 OminX GRUB and ISOLINUX menu templates
config/hooks/normal/                Multiarch, Steam, Wine, and Flathub setup
config/includes.chroot/             OminX branding, defaults, apps, and documentation
config/includes.binary/             Boot splash assets included on the ISO
scripts/check-config.sh             Static recipe and asset checks
scripts/generate-boot-splash.py     Dependency-free Aurora boot artwork generator
scripts/verify-boot-menu.sh         Post-build menu and installer verification
```

To change packages, edit `config/package-lists/ominx.list.chroot`. Build options live in `auto/config`. Build outputs and ISO artifacts are ignored by Git.

## Licensing and third-party software

The OminX project files and original artwork in this repository are covered by the repository's **GNU AGPLv3** license. The image combines Debian packages and third-party software that retain their own licenses and trademarks. Steam is proprietary software from Valve; non-free firmware is subject to its respective terms. OminX is an independent project and is not affiliated with or endorsed by Microsoft, Valve, or Debian.
