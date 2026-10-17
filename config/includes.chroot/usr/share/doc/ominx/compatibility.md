# OminX application and game compatibility

OminX is a Linux desktop. Windows programs run through compatibility layers, not a copy of Windows.

## Steam and Proton

Steam is included. Sign in to Steam, open **Settings → Compatibility**, and enable Steam Play for the games you want. Steam downloads the selected Valve Proton runtime when needed. The Proton runtime is delivered by Steam after sign-in; it is not copied into the ISO.

## Standalone Windows applications

Wine, 32-bit Wine support, Winetricks, and Lutris are installed. For a trusted installer, use the file manager's **Open With → Wine Windows Program Loader** option, or run:

```sh
wine "$HOME/Downloads/setup.exe"
```

Winetricks can add some common Windows libraries and fonts. Lutris can manage many games and launchers. The optional **OminX Protontricks** launcher installs Protontricks into your user account from PyPI the first time it is opened; it requires an internet connection.

## Compatibility limits

No Linux compatibility layer can run every Windows executable. Results depend on the exact application, its version, graphics hardware, drivers, and online services. Programs that require Windows kernel drivers, Windows Store/UWP, unsupported DRM, or Windows-only system services will generally not work. Some multiplayer games block Linux compatibility layers unless their publisher explicitly enables support.

Check the specific title before relying on it: [ProtonDB](https://www.protondb.com/) for Steam games and [Wine AppDB](https://appdb.winehq.org/) for Wine applications. Do not run an executable you do not trust; a Windows program launched through Wine can still access files in your user account.
