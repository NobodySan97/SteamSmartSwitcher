import os
import sys
import glob
import re
import json
import time
import shutil
import tempfile
import subprocess
import winreg
import ctypes
import shlex
from ctypes import wintypes
from PIL import Image, ImageDraw
import urllib.request

# Win32 Toolhelp32 Constants for native process checking (<0.2ms, 0% CPU)
TH32CS_SNAPPROCESS = 0x00000002

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * wintypes.MAX_PATH)
    ]

k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32FirstW.restype = wintypes.BOOL
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.CloseHandle.restype = wintypes.BOOL

def is_process_running_by_name(process_name: str) -> bool:
    """Zero-overhead Win32 snapshot process checker (<0.2ms, 0% CPU)."""
    h_snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snap == -1 or not h_snap:
        return False
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    target = process_name.lower()
    try:
        if k32.Process32FirstW(h_snap, ctypes.byref(entry)):
            while True:
                if entry.szExeFile.lower() == target:
                    return True
                if not k32.Process32NextW(h_snap, ctypes.byref(entry)):
                    break
    finally:
        k32.CloseHandle(h_snap)
    return False


class SteamCore:
    def __init__(self):
        self.steam_path = self.find_steam_path()
        self.steam_exe = os.path.join(self.steam_path, "Steam.exe")
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(self.base_dir, "cache")
        self.avatars_dir = os.path.join(self.cache_dir, "avatars")
        self.posters_dir = os.path.join(self.cache_dir, "posters")
        self.capsules_dir = os.path.join(self.cache_dir, "capsules")
        self.icons_dir = os.path.join(self.cache_dir, "icons")
        self.settings_file = os.path.join(self.base_dir, "user_settings.json")

        for d in [self.avatars_dir, self.posters_dir, self.capsules_dir, self.icons_dir]:
            os.makedirs(d, exist_ok=True)

        self.settings = self.load_settings()
        self._installed_games_cache = None
        self._installed_games_cache_time = 0

    def find_steam_path(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                path, _ = winreg.QueryValueEx(key, "SteamPath")
                return os.path.normpath(path)
        except Exception:
            pass

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                path, _ = winreg.QueryValueEx(key, "InstallPath")
                return os.path.normpath(path)
        except Exception:
            pass

        default_path = r"C:\Program Files (x86)\Steam"
        if os.path.exists(default_path):
            return default_path
        return r"C:\Steam"

    def load_settings(self):
        default_settings = {
            "account_tags": {},
            "launch_options": {},
            "view_mode": "grid",
            "autostart_windows": False,
            "start_minimized": False,
            "close_to_tray": True,
            "show_notifications": True,
            "auto_check_updates": True,
            "steam_silent_mode": True,
            "theme": "steam",
            "language": "it",
            "favorites": [],
            "sort_mode": "favorites",
            "github_repo": "NobodySan97/SteamSmartSwitcher",
            "default_account_on_boot": ""
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_settings.update(data)
            except Exception as e:
                print(f"Error loading settings: {e}")
        return default_settings

    def is_favorite(self, appid):
        favs = self.settings.get("favorites", [])
        return str(appid) in [str(x) for x in favs]

    def toggle_favorite(self, appid):
        appid_str = str(appid)
        favs = [str(x) for x in self.settings.get("favorites", [])]
        if appid_str in favs:
            favs.remove(appid_str)
            is_fav = False
        else:
            favs.append(appid_str)
            is_fav = True
        self.settings["favorites"] = favs
        self.save_settings()
        return is_fav

    def save_settings(self):
        temp_name = None
        try:
            settings_dir = os.path.dirname(self.settings_file)
            with tempfile.NamedTemporaryFile("w", dir=settings_dir, delete=False, encoding="utf-8") as tf:
                json.dump(self.settings, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.settings_file)
        except Exception as e:
            print(f"Error saving settings: {e}")
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except Exception:
                    pass

    def get_steam_active_info(self):
        res = {"steam_pid": 0, "active_user": "", "running_appid": 0}
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess")
            try:
                res["steam_pid"], _ = winreg.QueryValueEx(key, "pid")
            except Exception:
                pass
            try:
                res["active_user"], _ = winreg.QueryValueEx(key, "ActiveUser")
            except Exception:
                pass
            try:
                res["running_appid"], _ = winreg.QueryValueEx(key, "RunningAppID")
            except Exception:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass
        return res

    def is_game_running(self):
        """Returns (is_running, appid). Only evaluates if Steam is actively running to prevent stale registry false-positives."""
        if not self.is_steam_running():
            return False, 0
        info = self.get_steam_active_info()
        appid = info.get("running_appid", 0)
        return (appid != 0), appid

    def is_steam_running(self):
        """Zero-overhead Win32 snapshot process checker (<0.2ms, immune to stale registry PID reuse)."""
        return is_process_running_by_name("steam.exe")

    def close_steam_graceful(self, max_wait_seconds=15):
        is_playing, appid = self.is_game_running()
        if is_playing:
            raise RuntimeError(f"Impossibile cambiare account: Un gioco Steam (ID: {appid}) è attualmente in esecuzione!\nSalva e chiudi il gioco prima di effettuare lo switch.")

        if not self.is_steam_running():
            return True

        try:
            subprocess.Popen([self.steam_exe, "-shutdown"], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception as ex:
            print(f"[SteamLifecycle] -shutdown error: {ex}")

        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            if not self.is_steam_running():
                time.sleep(0.15)  # Settle time for OS kernel locks
                return True
            time.sleep(0.4)

        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "Stop-Process -Name steam -Force -ErrorAction SilentlyContinue"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            time.sleep(0.3)
        except Exception:
            pass

        return not self.is_steam_running()

    def get_current_auto_login_user(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                user, _ = winreg.QueryValueEx(key, "AutoLoginUser")
                return user.strip()
        except Exception:
            return ""

    def set_registry_auto_login(self, target_account):
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "AutoLoginUser", 0, winreg.REG_SZ, target_account)
                winreg.SetValueEx(key, "RememberPassword", 0, winreg.REG_DWORD, 1)
            return True
        except Exception as e:
            print(f"Error updating registry: {e}")
            return False

    def check_and_heal_vdf(self, vdf_path: str, bak_path: str):
        """Self-healing: Restores from .bak if loginusers.vdf is missing or 0 bytes."""
        try:
            if not os.path.exists(vdf_path) or os.path.getsize(vdf_path) == 0:
                if os.path.exists(bak_path) and os.path.getsize(bak_path) > 0:
                    shutil.copy2(bak_path, vdf_path)
                    print("[VDF] Restored corrupted/missing loginusers.vdf from .bak")
        except Exception as ex:
            print(f"[VDF] Self-healing error: {ex}")

    def update_loginusers_vdf(self, target_account: str) -> bool:
        vdf_path = os.path.join(self.steam_path, "config", "loginusers.vdf")
        bak_path = os.path.join(self.steam_path, "config", "loginusers.vdf.bak")

        self.check_and_heal_vdf(vdf_path, bak_path)

        if not os.path.exists(vdf_path):
            return False

        try:
            shutil.copy2(vdf_path, bak_path)
        except Exception as e:
            print(f"[VDF] Backup error: {e}")

        temp_name = None
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            target_clean = target_account.strip().lower()
            def block_replacer(match):
                steamid_header = match.group(1)
                block_inner = match.group(2)

                acc_match = re.search(r'"AccountName"\s*"([^"]+)"', block_inner, re.IGNORECASE)
                is_target = acc_match and (acc_match.group(1).strip().lower() == target_clean)
                flag = "1" if is_target else "0"

                # Update or set mostrecent / MostRecent
                if re.search(r'"mostrecent"\s*"[^"]*"', block_inner, re.IGNORECASE):
                    block_inner = re.sub(r'"mostrecent"\s*"[^"]*"', f'"mostrecent"\t\t"{flag}"', block_inner, flags=re.IGNORECASE)
                elif re.search(r'"MostRecent"\s*"[^"]*"', block_inner):
                    block_inner = re.sub(r'"MostRecent"\s*"[^"]*"', f'"MostRecent"\t\t"{flag}"', block_inner)
                else:
                    block_inner += f'\n\t\t"mostrecent"\t\t"{flag}"'

                # Update AutoLogin / AllowAutoLogin if present
                if re.search(r'"AutoLogin"\s*"[^"]*"', block_inner, re.IGNORECASE):
                    block_inner = re.sub(r'"AutoLogin"\s*"[^"]*"', f'"AutoLogin"\t\t"{flag}"', block_inner, flags=re.IGNORECASE)

                if re.search(r'"AllowAutoLogin"\s*"[^"]*"', block_inner, re.IGNORECASE):
                    block_inner = re.sub(r'"AllowAutoLogin"\s*"[^"]*"', f'"AllowAutoLogin"\t\t"{flag}"', block_inner, flags=re.IGNORECASE)

                # Ensure RememberPassword is 1 and WantsOfflineMode is 0 for target
                if is_target:
                    if re.search(r'"RememberPassword"\s*"[^"]*"', block_inner, re.IGNORECASE):
                        block_inner = re.sub(r'"RememberPassword"\s*"[^"]*"', f'"RememberPassword"\t\t"1"', block_inner, flags=re.IGNORECASE)
                    if re.search(r'"WantsOfflineMode"\s*"[^"]*"', block_inner, re.IGNORECASE):
                        block_inner = re.sub(r'"WantsOfflineMode"\s*"[^"]*"', f'"WantsOfflineMode"\t\t"0"', block_inner, flags=re.IGNORECASE)

                return f'{steamid_header}{{{block_inner}\n\t}}'

            pattern = re.compile(r'("\d{17}"\s*[\r\n]+\t*)\{([\s\S]*?)\n\t*\}', re.MULTILINE)
            updated_content, count = pattern.subn(block_replacer, content)

            if count == 0:
                return False

            config_dir = os.path.dirname(vdf_path)
            with tempfile.NamedTemporaryFile("w", dir=config_dir, delete=False, encoding="utf-8") as tf:
                tf.write(updated_content)
                temp_name = tf.name

            # Atomic replace with retry for file-lock contention
            replaced = False
            for attempt in range(5):
                try:
                    os.replace(temp_name, vdf_path)
                    replaced = True
                    temp_name = None
                    break
                except (PermissionError, OSError):
                    time.sleep(0.2)

            if not replaced:
                raise OSError("Impossibile salvare loginusers.vdf: il file è bloccato da un altro processo.")

            return True

        except Exception as ex:
            print(f"[VDF] Critical error: {ex}")
            if os.path.exists(bak_path):
                try:
                    shutil.copy2(bak_path, vdf_path)
                except Exception:
                    pass
            return False
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except Exception:
                    pass

    def switch_account_and_launch(self, target_account, appid=None, launch_args=""):
        current_user = self.get_current_auto_login_user().lower()
        target_clean = target_account.strip().lower()
        is_running = self.is_steam_running()

        # If Steam is already running with the target account, launch directly via Windows Shell
        if is_running and current_user == target_clean:
            if appid:
                if launch_args:
                    import urllib.parse
                    encoded_args = urllib.parse.quote(launch_args.strip())
                    try:
                        os.startfile(f"steam://run/{appid}//{encoded_args}/")
                    except Exception:
                        os.startfile(f"steam://rungameid/{appid}")
                else:
                    os.startfile(f"steam://rungameid/{appid}")
            return True

        # If Steam is running with another account, close it gracefully
        if is_running:
            self.close_steam_graceful()
            time.sleep(0.3)

        # Update Registry and loginusers.vdf
        self.set_registry_auto_login(target_account)
        if not self.update_loginusers_vdf(target_account):
            raise RuntimeError(f"Impossibile aggiornare loginusers.vdf per l'account '{target_account}'.")

        # Launch Steam via Windows Shell to ensure trusted parent process (explorer.exe)
        try:
            os.startfile(self.steam_exe)
        except Exception:
            subprocess.Popen([self.steam_exe], creationflags=subprocess.DETACHED_PROCESS if os.name == 'nt' else 0)

        # If a game was requested, wait for Steam process to start, then trigger game launch via Shell
        if appid:
            def _launch_game_delayed():
                for _ in range(20):
                    if self.is_steam_running():
                        break
                    time.sleep(0.5)
                time.sleep(1.5)  # Let Steam client finish initial auth handshake
                if launch_args:
                    import urllib.parse
                    encoded_args = urllib.parse.quote(launch_args.strip())
                    try:
                        os.startfile(f"steam://run/{appid}//{encoded_args}/")
                    except Exception:
                        os.startfile(f"steam://rungameid/{appid}")
                else:
                    os.startfile(f"steam://rungameid/{appid}")

            threading.Thread(target=_launch_game_delayed, daemon=True).start()

        return True

    def get_account_tag(self, account_name):
        return self.settings.get("account_tags", {}).get(account_name.lower(), "")

    def set_account_tag(self, account_name, tag):
        if "account_tags" not in self.settings:
            self.settings["account_tags"] = {}
        self.settings["account_tags"][account_name.lower()] = tag.strip()
        self.save_settings()

    def get_game_launch_options(self, appid, account_name=""):
        opts_dict = self.settings.get("launch_options", {})
        key_acc = f"{appid}_{account_name.lower()}" if account_name else ""
        if key_acc and key_acc in opts_dict:
            return opts_dict[key_acc]
        return opts_dict.get(str(appid), "")

    def set_game_launch_options(self, appid, launch_args, account_name=""):
        if "launch_options" not in self.settings:
            self.settings["launch_options"] = {}
        key = f"{appid}_{account_name.lower()}" if account_name else str(appid)
        if launch_args.strip():
            self.settings["launch_options"][key] = launch_args.strip()
        else:
            self.settings["launch_options"].pop(key, None)
        self.save_settings()

    def is_windows_autostart_enabled(self):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "SteamSmartSwitcher")
                return True, val
        except Exception:
            return False, ""

    def set_windows_autostart(self, enable=True, start_minimized=False):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    if getattr(sys, 'frozen', False):
                        exe_path = sys.executable
                        cmd = f'"{exe_path}"'
                    else:
                        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                        main_py = os.path.join(self.base_dir, "main.py")
                        cmd = f'"{python_exe}" "{main_py}"'

                    if start_minimized:
                        cmd += " --minimized"

                    winreg.SetValueEx(key, "SteamSmartSwitcher", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "SteamSmartSwitcher")
                    except FileNotFoundError:
                        pass
            self.settings["autostart_windows"] = enable
            self.save_settings()
            return True
        except Exception as e:
            print(f"Error updating autostart registry: {e}")
            return False

    def apply_boot_default_account(self):
        default_acc = self.settings.get("default_account_on_boot", "").strip()
        if not default_acc:
            return False

        if not self.is_steam_running():
            self.set_registry_auto_login(default_acc)
            self.update_loginusers_vdf(default_acc)
            return True
        return False

    def get_existing_smart_shortcuts(self):
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        shortcuts = []

        all_lnks = glob.glob(os.path.join(desktop, "*.lnk"))
        all_lnks += glob.glob(os.path.join(desktop, "Steam - *", "*.lnk"))

        try:
            import win32com.client
            wscript = win32com.client.Dispatch("WScript.Shell")
        except Exception:
            wscript = None

        if not wscript:
            return shortcuts

        for lnk in all_lnks:
            try:
                sc = wscript.CreateShortcut(lnk)
                args = sc.Arguments
                if "--appid" in args and "--account" in args:
                    appid_m = re.search(r'--appid\s+["\']?(\d+)["\']?', args)
                    acc_m = re.search(r'--account\s+["\']?([^"\']+)["\']?', args)
                    opts_m = re.search(r'--args\s+["\']([^"\']*)["\']', args)

                    folder = "Desktop" if os.path.dirname(lnk) == desktop else os.path.basename(os.path.dirname(lnk))
                    shortcuts.append({
                        "path": lnk,
                        "filename": os.path.basename(lnk),
                        "folder": folder,
                        "appid": appid_m.group(1) if appid_m else "N/D",
                        "account": acc_m.group(1) if acc_m else "N/D",
                        "launch_args": opts_m.group(1) if opts_m else ""
                    })
            except Exception:
                pass

        return shortcuts

    def open_game_directory(self, full_dir):
        if full_dir and os.path.exists(full_dir):
            os.startfile(full_dir)

    def open_store_page(self, appid):
        os.startfile(f"https://store.steampowered.com/app/{appid}")

    def open_community_profile(self, steamid):
        os.startfile(f"https://steamcommunity.com/profiles/{steamid}")

    def create_desktop_shortcut(self, appid, game_name, account_name, persona_name, launch_args="", target_dir=None):
        if target_dir is None:
            target_dir = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")

        os.makedirs(target_dir, exist_ok=True)
        clean_game_name = re.sub(r'[\\/*?:"<>|]', "", game_name)
        clean_persona = re.sub(r'[\\/*?:"<>|]', "", persona_name)
        shortcut_filename = f"{clean_game_name} ({clean_persona}).lnk"
        shortcut_path = os.path.join(target_dir, shortcut_filename)

        icon_source = self.get_cached_icon_path(appid)
        if not icon_source or not os.path.exists(icon_source):
            game_data = next((g for g in self.get_installed_games() if str(g["appid"]) == str(appid)), None)
            icon_source = game_data["icon_path"] if game_data else None
        if not icon_source or not os.path.exists(icon_source):
            icon_source = self.steam_exe

        target_exe = sys.executable if getattr(sys, 'frozen', False) else os.path.join(self.base_dir, "SteamSmartSwitcher.exe")
        if not os.path.exists(target_exe):
            target_exe = sys.executable

        if getattr(sys, 'frozen', False) or target_exe.endswith("SteamSmartSwitcher.exe"):
            arguments = f'--appid {appid} --account "{account_name}"'
        else:
            arguments = f'--appid {appid} --account "{account_name}"'

        if launch_args:
            arguments += f' --args "{launch_args}"'

        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.TargetPath = target_exe
            shortcut.Arguments = arguments
            shortcut.WorkingDirectory = self.base_dir
            shortcut.IconLocation = f"{icon_source},0"
            shortcut.Description = f"Avvia {game_name} con account {persona_name}"
            shortcut.Save()
            return shortcut_path
        except Exception:
            ps_target = target_exe.replace("'", "''")
            ps_args = arguments.replace("'", "''")
            ps_dir = self.base_dir.replace("'", "''")
            ps_icon = f"{icon_source},0".replace("'", "''")
            ps_link = shortcut_path.replace("'", "''")
            ps_script = f"$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('{ps_link}'); $s.TargetPath = '{ps_target}'; $s.Arguments = '{ps_args}'; $s.WorkingDirectory = '{ps_dir}'; $s.IconLocation = '{ps_icon}'; $s.Save()"
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return shortcut_path

    def create_all_shortcuts_for_account(self, account_name, persona_name, in_subfolder=True):
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        clean_persona = re.sub(r'[\\/*?:"<>|]', "", persona_name)
        if in_subfolder:
            target_dir = os.path.join(desktop, f"Steam - {clean_persona}")
        else:
            target_dir = desktop

        os.makedirs(target_dir, exist_ok=True)
        games = self.get_installed_games()
        created = []

        for g in games:
            appid = g["appid"]
            name = g["name"]
            l_args = self.get_game_launch_options(appid, account_name)
            p = self.create_desktop_shortcut(appid, name, account_name, persona_name, launch_args=l_args, target_dir=target_dir)
            created.append(p)

        return target_dir, created

    def get_remembered_accounts(self):
        vdf_path = os.path.join(self.steam_path, "config", "loginusers.vdf")
        bak_path = os.path.join(self.steam_path, "config", "loginusers.vdf.bak")
        self.check_and_heal_vdf(vdf_path, bak_path)

        if not os.path.exists(vdf_path):
            return []

        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return []

        current_active = self.get_current_auto_login_user().lower()
        accounts = []
        user_blocks = re.findall(r'"(\d{17})"\s*\{([^}]+)\}', content, re.MULTILINE)

        for steamid, block in user_blocks:
            acc_name_m = re.search(r'"AccountName"\s*"([^"]+)"', block, re.IGNORECASE)
            persona_m = re.search(r'"PersonaName"\s*"([^"]+)"', block, re.IGNORECASE)
            mostrecent_m = re.search(r'"(?:mostrecent|MostRecent)"\s*"([^"]+)"', block, re.IGNORECASE)
            autologin_m = re.search(r'"AutoLogin"\s*"([^"]+)"', block, re.IGNORECASE)

            if acc_name_m:
                acc_name = acc_name_m.group(1)
                persona = persona_m.group(1) if persona_m else acc_name
                is_active = (acc_name.lower() == current_active)
                if not current_active and mostrecent_m and mostrecent_m.group(1) == "1":
                    is_active = True

                accounts.append({
                    "steamid": steamid,
                    "account_name": acc_name,
                    "persona_name": persona,
                    "is_active": is_active,
                    "mostrecent": mostrecent_m.group(1) if mostrecent_m else "0",
                    "autologin": autologin_m.group(1) if autologin_m else "0"
                })

        accounts.sort(key=lambda x: (not x["is_active"], x["persona_name"].lower()))
        return accounts

    def get_cached_avatar_path(self, steamid):
        cached = os.path.join(self.avatars_dir, f"{steamid}.png")
        return cached if os.path.exists(cached) else None

    def fetch_and_cache_avatar(self, steamid, persona_name=""):
        cached = os.path.join(self.avatars_dir, f"{steamid}.png")
        if os.path.exists(cached):
            return cached

        try:
            url = f"https://steamcommunity.com/profiles/{steamid}?xml=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                xml_data = resp.read().decode("utf-8", errors="ignore")

            m = re.search(r'<avatarMedium><!\[CDATA\[(.*?)\]\]></avatarMedium>', xml_data) or \
                re.search(r'<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>', xml_data) or \
                re.search(r'<avatarIcon><!\[CDATA\[(.*?)\]\]></avatarIcon>', xml_data)

            if m:
                avatar_url = m.group(1)
                req2 = urllib.request.Request(avatar_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req2, timeout=3) as resp2:
                    with open(cached, "wb") as f:
                        f.write(resp2.read())
                return cached
        except Exception:
            pass

        img = Image.new("RGBA", (64, 64), color=(31, 42, 56, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([(2, 2), (61, 61)], outline=(102, 192, 244, 255), width=2)
        initials = (persona_name[:2] if persona_name else "U").upper()
        d.text((22, 24), initials, fill=(255, 255, 255, 255))
        img.save(cached, format="PNG")
        return cached

    def get_library_folders(self):
        folders = [self.steam_path]
        library_vdf = os.path.join(self.steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(library_vdf):
            try:
                with open(library_vdf, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # Support both modern "path" and legacy "1" "path"
                paths = re.findall(r'"path"\s*"([^"]+)"', content)
                paths += re.findall(r'"\d+"\s*"([^"]+)"', content)
                for p in paths:
                    norm_p = os.path.normpath(p.replace("\\\\", "\\"))
                    if os.path.exists(norm_p) and not any(os.path.samefile(norm_p, f) for f in folders if os.path.exists(f)):
                        folders.append(norm_p)
            except Exception as e:
                print(f"Error reading libraryfolders.vdf: {e}")
        return folders

    def get_url_shortcuts_map(self):
        shortcuts_map = {}
        scan_dirs = [
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Steam"),
            os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Steam"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        ]
        for d in scan_dirs:
            if not os.path.exists(d):
                continue
            for file in glob.glob(os.path.join(d, "*.url")):
                try:
                    with open(file, "r", encoding="utf-8", errors="ignore") as f:
                        txt = f.read()
                    appid_m = re.search(r"URL=steam://rungameid/(\d+)", txt, re.IGNORECASE)
                    icon_m = re.search(r"IconFile=([^\r\n]+)", txt, re.IGNORECASE)
                    if appid_m and icon_m:
                        appid = appid_m.group(1)
                        icon_path = icon_m.group(1).strip()
                        if os.path.exists(icon_path):
                            shortcuts_map[appid] = icon_path
                except Exception:
                    pass
        return shortcuts_map

    def get_installed_games(self, force_refresh=False):
        # Cache for 10 seconds to eliminate disk thrashing during tray redraws
        now = time.time()
        if not force_refresh and self._installed_games_cache and (now - self._installed_games_cache_time < 10):
            return self._installed_games_cache

        url_icons = self.get_url_shortcuts_map()
        games = []
        seen_appids = set()
        exclude_appids = {"228980", "1391110", "1493710"}

        for lib in self.get_library_folders():
            steamapps_dir = os.path.join(lib, "steamapps") if not lib.endswith("steamapps") else lib
            manifests = glob.glob(os.path.join(steamapps_dir, "appmanifest_*.acf"))
            for mf in manifests:
                try:
                    with open(mf, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    appid_m = re.search(r'"appid"\s*"(\d+)"', content)
                    name_m = re.search(r'"name"\s*"([^"]+)"', content)
                    installdir_m = re.search(r'"installdir"\s*"([^"]+)"', content)
                    size_m = re.search(r'"SizeOnDisk"\s*"(\d+)"', content)
                    last_played_m = re.search(r'"LastPlayed"\s*"(\d+)"', content)
                    last_owner_m = re.search(r'"LastOwner"\s*"([^"]+)"', content)

                    if appid_m and name_m:
                        appid = appid_m.group(1)
                        name = name_m.group(1)
                        installdir = installdir_m.group(1) if installdir_m else ""
                        size_bytes = int(size_m.group(1)) if size_m else 0
                        last_played_ts = int(last_played_m.group(1)) if last_played_m else 0
                        last_owner_id = last_owner_m.group(1) if last_owner_m else ""

                        if appid in seen_appids or appid in exclude_appids:
                            continue
                        seen_appids.add(appid)

                        if size_bytes >= 1073741824:
                            size_str = f"{size_bytes / 1073741824:.2f} GB"
                        else:
                            size_str = f"{size_bytes / 1048576:.0f} MB"

                        if last_played_ts > 0:
                            last_played_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(last_played_ts))
                        else:
                            last_played_str = "Mai"

                        drive = os.path.splitdrive(lib)[0].upper() or "C:"
                        full_dir = os.path.join(steamapps_dir, "common", installdir) if installdir else ""

                        icon_path = self.resolve_game_icon(appid, name, installdir, lib, url_icons)
                        poster_path = self.get_cached_poster_path(appid)
                        capsule_path = self.get_cached_capsule_path(appid)

                        games.append({
                            "appid": appid,
                            "name": name,
                            "installdir": installdir,
                            "full_dir": full_dir,
                            "library": lib,
                            "drive": drive,
                            "size_bytes": size_bytes,
                            "size_str": size_str,
                            "last_played_ts": last_played_ts,
                            "last_played_str": last_played_str,
                            "last_owner_id": last_owner_id,
                            "icon_path": icon_path,
                            "poster_path": poster_path,
                            "capsule_path": capsule_path
                        })
                except Exception as e:
                    print(f"Error reading manifest {mf}: {e}")

        games.sort(key=lambda g: g["name"].lower())
        self._installed_games_cache = games
        self._installed_games_cache_time = now
        return games

    def get_game_ownership(self, game, account, all_accounts, i18n=None):
        def _t(k, **kw):
            return i18n.t(k, **kw) if i18n else (k.replace("_", " ").title())

        if not account or not game:
            return {"is_owner": True, "badge_text": _t("badge_owned_list") if i18n else "👑 Di Proprietà", "is_shared": False}

        game_owner_id = game.get("last_owner_id", "")
        account_steamid = account.get("steamid", "")

        if not game_owner_id or game_owner_id == "0":
            return {"is_owner": True, "badge_text": _t("badge_owned_list") if i18n else "👑 Di Proprietà", "is_shared": False}

        if game_owner_id == account_steamid:
            return {"is_owner": True, "badge_text": _t("badge_owned_list") if i18n else "👑 Di Proprietà", "is_shared": False}

        owner_acc = next((a for a in all_accounts if a["steamid"] == game_owner_id), None)
        if owner_acc:
            b_text = _t("badge_shared_list", owner=owner_acc['persona_name']) if i18n else f"👨‍👩‍👧‍👦 Condiviso da {owner_acc['persona_name']}"
            return {
                "is_owner": False,
                "badge_text": b_text,
                "is_shared": True,
                "owner_name": owner_acc['persona_name']
            }

        return {"is_owner": False, "badge_text": _t("badge_shared_generic") if i18n else "👨‍👩‍👧‍👦 Family Sharing", "is_shared": True}

    def get_cached_icon_path(self, appid):
        """Returns the cached icon path or resolves from game manifest / Steam cache."""
        custom_icon = os.path.join(self.icons_dir, f"{appid}.ico")
        if os.path.exists(custom_icon):
            return custom_icon

        appinfo_icon = os.path.join(self.steam_path, "steam", "games", f"{appid}.ico")
        if os.path.exists(appinfo_icon):
            return appinfo_icon

        for game in self.get_installed_games():
            if str(game["appid"]) == str(appid):
                if game.get("icon_path") and os.path.exists(game["icon_path"]):
                    return game["icon_path"]
                break

        return self.steam_exe

    def resolve_game_icon(self, appid, name, installdir, library_path, url_icons=None):
        custom_icon = os.path.join(self.icons_dir, f"{appid}.ico")
        if os.path.exists(custom_icon):
            return custom_icon

        if url_icons and appid in url_icons and os.path.exists(url_icons[appid]):
            return url_icons[appid]

        steamapps = os.path.join(library_path, "steamapps") if not library_path.endswith("steamapps") else library_path
        common_game = os.path.join(steamapps, "common", installdir)
        if os.path.exists(common_game):
            for exe in glob.glob(os.path.join(common_game, "*.exe")):
                base = os.path.basename(exe).lower()
                if "crash" not in base and "unins" not in base and "helper" not in base and "setup" not in base:
                    return exe
            for exe in glob.glob(os.path.join(common_game, "**", "*.exe"), recursive=True):
                base = os.path.basename(exe).lower()
                if "crash" not in base and "unins" not in base and "helper" not in base and "setup" not in base:
                    return exe

        appinfo_icon = os.path.join(self.steam_path, "steam", "games", f"{appid}.ico")
        if os.path.exists(appinfo_icon):
            return appinfo_icon

        return self.steam_exe

    def get_cached_poster_path(self, appid):
        local_grid = os.path.join(self.steam_path, "userdata")
        for ufolder in glob.glob(os.path.join(local_grid, "*", "config", "grid", f"{appid}p.*")):
            if os.path.exists(ufolder):
                return ufolder
        for ufolder in glob.glob(os.path.join(local_grid, "*", "config", "grid", f"{appid}.*")):
            if os.path.exists(ufolder):
                return ufolder

        cached = os.path.join(self.posters_dir, f"{appid}.jpg")
        return cached if os.path.exists(cached) else None

    def get_cached_capsule_path(self, appid):
        cached = os.path.join(self.capsules_dir, f"{appid}.jpg")
        return cached if os.path.exists(cached) else None

    def fetch_and_cache_game_images(self, appid, game_name=""):
        poster_file = os.path.join(self.posters_dir, f"{appid}.jpg")
        capsule_file = os.path.join(self.capsules_dir, f"{appid}.jpg")

        if not os.path.exists(poster_file):
            urls_to_try = [
                f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/library_600x900_2x.jpg",
                f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/library_600x900.jpg",
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
            ]
            downloaded = False
            for u in urls_to_try:
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        with open(poster_file, "wb") as f:
                            f.write(resp.read())
                    downloaded = True
                    break
                except Exception:
                    pass

            if not downloaded:
                img = Image.new("RGBA", (300, 450), color=(27, 40, 56, 255))
                d = ImageDraw.Draw(img)
                d.rectangle([(2, 2), (297, 447)], outline=(102, 192, 244, 255), width=2)
                short_t = game_name[:15] if game_name else f"App {appid}"
                d.text((40, 200), short_t, fill=(255, 255, 255, 255))
                img.convert("RGB").save(poster_file, format="JPEG")

        if not os.path.exists(capsule_file):
            u = f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    with open(capsule_file, "wb") as f:
                        f.write(resp.read())
            except Exception:
                pass

        return poster_file, capsule_file
