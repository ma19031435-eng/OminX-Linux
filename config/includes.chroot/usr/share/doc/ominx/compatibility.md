# OminX application and game compatibility

OminX is a Linux desktop. Windows programs run through compatibility layers, not a copy of Windows.

## Steam and Proton

Steam is included. Sign in to Steam, open **Settings → Compatibility**, and enable Steam Play for the games you want. Steam downloads the selected Valve Proton runtime when needed. The Proton runtime is delivered by Steam after sign-in; it is not copied into the ISO.

## Standalone Windows applications

Wine, 32-bit Wine support, Winetricks, and Lutris are installed. Double-click a trusted `.exe` or `.msi` file to open it with **OminX Windows App Support**. EXE installers run through Wine; MSI packages are passed to Wine's Windows Installer. If another app opens the file, use **Open With → OminX Windows App Support**. You can also open **OminX Windows App Support** from the Applications menu and choose a file.

The first launch may take longer while Wine creates your personal Windows-compatible environment in `~/.wine`; Wine may also offer to install helper components. Complete the installer's own prompts. A successfully installed program may add a shortcut to the Applications menu; otherwise, double-click its installed `.exe` or open it through Wine. Installers and apps share the default Wine environment unless you use a separate Wine prefix.

Winetricks can add some common Windows libraries and fonts. Lutris can manage many games and launchers. The optional **OminX Protontricks** launcher installs Protontricks into your user account from PyPI the first time it is opened; it requires an internet connection.

Only open files from sources you trust. Wine programs are not sandboxed and can access or modify files in your user account. Double-click support does not make every Windows program compatible; check the limitations below before relying on an app.

## Compatibility limits

No Linux compatibility layer can run every Windows executable. Results depend on the exact application, its version, graphics hardware, drivers, and online services. Programs that require Windows kernel drivers, Windows Store/UWP, unsupported DRM, or Windows-only system services will generally not work. Some multiplayer games block Linux compatibility layers unless their publisher explicitly enables support.

Check the specific title before relying on it: [ProtonDB](https://www.protondb.com/) for Steam games and [Wine AppDB](https://appdb.winehq.org/) for Wine applications. Do not run an executable you do not trust; a Windows program launched through Wine can still access files in your user account.
