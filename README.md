# 🎮 Steam Smart Account Switcher & Game Launcher

<div align="center">

[![GitHub Release](https://img.shields.io/github/v/release/NobodySan97/SteamSmartSwitcher?style=flat-square&color=66c0f4)](https://github.com/NobodySan97/SteamSmartSwitcher/releases/latest)
[![Total Downloads](https://img.shields.io/github/downloads/NobodySan97/SteamSmartSwitcher/total.svg?style=flat-square&logo=github&color=5c7e10)](https://github.com/NobodySan97/SteamSmartSwitcher/releases)
[![Latest Downloads](https://img.shields.io/github/downloads/NobodySan97/SteamSmartSwitcher/latest/total.svg?style=flat-square&logo=github&color=66c0f4)](https://github.com/NobodySan97/SteamSmartSwitcher/releases/latest)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg?style=flat-square&logo=windows)](https://github.com/NobodySan97/SteamSmartSwitcher)

**The intelligent Steam multi-account switcher: creates desktop game shortcuts that automatically switch accounts and launch games in a single click.**

---

### 🌐 Language / Lingua
**English** • [🇮🇹 Leggi la documentazione in Italiano](README_IT.md)

---

> [!WARNING]
> **Work In Progress (WIP) — Untested Early Build**  
> This project is currently in active early development and **has not been thoroughly tested yet** across different hardware setups, Steam configurations, and Windows environments. Bugs or unexpected behavior may occur. Use at your own discretion and feel free to report issues!

---

</div>

## 🌟 Key Features

- ⚡ **1-Click Smart Shortcut Routing**: Double-click any game shortcut created on your desktop: if you're not logged into the correct Steam account, Steam is automatically restarted and logged into the right account (zero password prompts), launching your game immediately.
- 📦 **All-in-One Standalone Executable (`.exe`)**: No Python installation required for end users. The binary operates as a full GUI with dark Steam aesthetics when launched normally, and as an ultra-fast headless launcher (<15ms) when triggered from shortcuts.
- 🎨 **Modern Steam Dark UI & Visual Assets**: Automatically detects all configured accounts, downloads and displays real Steam Community avatars, and renders game libraries in both Poster Grid and Detailed List views.
- 🌈 **5 Built-in Color Themes**: Customize the entire client interface with **Steam Dark**, **OLED Pure Black** (for OLED displays), **Cyberpunk Neon**, **Midnight Blue**, or **Nordic Forest**.
- 👑 **License & 👨‍👩‍👧‍👦 Family Sharing Detection**: Automatically distinguishes games owned natively by the selected account from games shared across local profiles via Steam Family Sharing.
- 🔔 **Windows System Tray Integration**: Minimizes cleanly to the taskbar notification area next to the Windows clock, featuring a right-click context menu for instant account switching and game launching.
- ⚙️ **Per-Account Custom Launch Options**: Store tailored launch parameters (e.g. `-novid -high +exec smurf.cfg`) per account and game.
- 🛡️ **Active Game & Steam Cloud Protection**: Prevents accidental account switches while a Steam game is running to safeguard savegames and cloud sync.
- 🌍 **Multi-Language Support**: Complete interface translation with support for **English** and **Italian**.
- 🔄 **Built-in GitHub Auto-Updater**: Detects new GitHub releases and updates itself with a single click.

---

## 📥 Download & Installation

1. Download the latest **`SteamSmartSwitcher.exe`** from the [GitHub Releases Page](https://github.com/NobodySan97/SteamSmartSwitcher/releases/latest).
2. Move `SteamSmartSwitcher.exe` into a folder of your choice (e.g. `C:\Program Files\SteamSmartLauncher` or your Documents).
3. Run `SteamSmartSwitcher.exe`.

> [!TIP]
> To launch the switcher automatically on Windows startup, open **Settings ⚙️** inside the app and enable *"Start automatically when Windows boots"*.

---

## 🕹️ How It Works

```
                    [ Double-click Game Shortcut ]
                                  │
                                  ▼
                     [ SteamSmartSwitcher.exe ]
                                  │
                    Is target account active?
                             ╱           ╲
                       YES  ╱             ╲  NO
                           ╱               ╲
                          ▼                 ▼
                  Launch game directly     1. Gracefully close Steam
                                           2. Atomic update of Registry & VDF
                                           3. Relaunch Steam with target user
                                           4. Start the game!
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + F` or `/` | Focus search bar |
| `Enter` | Launch selected game with selected account |
| `Esc` | Clear search query or minimize to tray |
| `F5` or `Ctrl + R` | Refresh and rescan Steam accounts & library |
| `Ctrl + ,` | Open Settings dialog |

---

## 🛠️ Building from Source

```bash
# 1. Clone repository
git clone https://github.com/NobodySan97/SteamSmartSwitcher.git
cd SteamSmartSwitcher

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build standalone .exe
python -m PyInstaller --noconsole --onefile --name="SteamSmartSwitcher" --icon="C:\Program Files (x86)\Steam\Steam.exe" --clean main.py
```

The compiled binary will be located at `dist/SteamSmartSwitcher.exe`.

---

## 📄 License

Distributed under the **MIT** License. See [`LICENSE`](LICENSE) for more information.
