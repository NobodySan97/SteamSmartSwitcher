import os
import sys
import glob
import json
import time
import shutil
import tempfile
import subprocess
import winreg
import re
import datetime
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw
import requests
import io
import xml.etree.ElementTree as ET

try:
    import win32com.client
except ImportError:
    win32com = None

class SteamCore:
    def __init__(self):
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.icons_dir = os.path.join(self.base_dir, "icons")
        self.avatars_dir = os.path.join(self.icons_dir, "avatars")
        self.posters_dir = os.path.join(self.icons_dir, "posters")
        self.capsules_dir = os.path.join(self.icons_dir, "capsules")
        self.settings_file = os.path.join(self.base_dir, "user_settings.json")
        self.compiled_exe = os.path.join(self.base_dir, "SteamSmartSwitcher.exe")

        for d in [self.icons_dir, self.avatars_dir, self.posters_dir, self.capsules_dir]:
            os.makedirs(d, exist_ok=True)

        self.steam_path = self.detect_steam_path()
        self.steam_exe = os.path.join(self.steam_path, "Steam.exe")
        self.settings = self.load_settings()

    def detect_steam_path(self):
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
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_steam_active_info(self):
        info = {"running_appid": 0, "steam_pid": 0, "active_user": 0}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
                try:
                    info["running_appid"], _ = winreg.QueryValueEx(key, "RunningAppID")
                except Exception:
                    pass
                try:
                    info["steam_pid"], _ = winreg.QueryValueEx(key, "pid")
                except Exception:
                    pass
                try:
                    info["active_user"], _ = winreg.QueryValueEx(key, "ActiveUser")
                except Exception:
                    pass
        except Exception:
            pass
        return info

    def is_game_running(self):
        info = self.get_steam_active_info()
        return (info["running_appid"] != 0), info["running_appid"]

    def is_steam_running(self):
        info = self.get_steam_active_info()
        pid = info["steam_pid"]
        if pid and pid > 0:
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                exit_code = wintypes.DWORD()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                return exit_code.value == 259
        
        try:
            cmd = 'tasklist /FI "IMAGENAME eq steam.exe" /NH'
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            return "steam.exe" in output.lower()
        except Exception:
            return False

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
                time.sleep(0.5)
                return True
            time.sleep(0.5)

        try:
            subprocess.run("taskkill /F /IM steam.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
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
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "AutoLoginUser", 0, winreg.REG_SZ, target_account)
                winreg.SetValueEx(key, "RememberPassword", 0, winreg.REG_DWORD, 1)
            return True
        except Exception as e:
            print(f"Error updating registry: {e}")
            return False

    def update_loginusers_vdf(self, target_account: str) -> bool:
        vdf_path = os.path.join(self.steam_path, "config", "loginusers.vdf")
        bak_path = os.path.join(self.steam_path, "config", "loginusers.vdf.bak")

        if not os.path.exists(vdf_path):
            return False

        try:
            shutil.copy2(vdf_path, bak_path)
        except Exception as e:
            print(f"[VDF] Backup error: {e}")

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

                if re.search(r'"AutoLogin"\s*"[^"]*"', block_inner, re.IGNORECASE):
                    block_inner = re.sub(r'"AutoLogin"\s*"[^"]*"', f'"AutoLogin"\t\t"{flag}"', block_inner, flags=re.IGNORECASE)
                else:
                    block_inner += f'\n\t\t"AutoLogin"\t\t"{flag}"'

                if re.search(r'"AllowAutoLogin"\s*"[^"]*"', block_inner, re.IGNORECASE):
                    block_inner = re.sub(r'"AllowAutoLogin"\s*"[^"]*"', f'"AllowAutoLogin"\t\t"{flag}"', block_inner, flags=re.IGNORECASE)

                if re.search(r'"mostrecent"\s*"[^"]*"', block_inner, re.IGNORECASE):
                    block_inner = re.sub(r'"mostrecent"\s*"[^"]*"', f'"mostrecent"\t\t"{flag}"', block_inner, flags=re.IGNORECASE)
                elif re.search(r'"MostRecent"\s*"[^"]*"', block_inner):
                    block_inner = re.sub(r'"MostRecent"\s*"[^"]*"', f'"MostRecent"\t\t"{flag}"', block_inner)
                else:
                    block_inner += f'\n\t\t"mostrecent"\t\t"{flag}"'

                return f'{steamid_header}{{{block_inner}\n\t}}'

            pattern = re.compile(r'("\d{17}"\s*[\r\n]+\t*)\{([\s\S]*?)\n\t*\}', re.MULTILINE)
            updated_content, count = pattern.subn(block_replacer, content)

            if count == 0:
                return False

            config_dir = os.path.dirname(vdf_path)
            with tempfile.NamedTemporaryFile("w", dir=config_dir, delete=False, encoding="utf-8") as tf:
                tf.write(updated_content)
                temp_name = tf.name

            os.replace(temp_name, vdf_path)
            return True

        except Exception as ex:
            print(f"[VDF] Critical error: {ex}")
            if os.path.exists(bak_path):
                try:
                    shutil.copy2(bak_path, vdf_path)
                except Exception:
                    pass
            return False

    def switch_account_and_launch(self, target_account, appid=None, launch_args=""):
        current_user = self.get_current_auto_login_user().lower()
        target_clean = target_account.strip().lower()
        is_running = self.is_steam_running()

        if is_running and current_user == target_clean:
            if appid:
                if launch_args:
                    cmd = [self.steam_exe, "-applaunch", str(appid)] + launch_args.split()
                    subprocess.Popen(cmd)
                else:
                    os.startfile(f"steam://rungameid/{appid}")
            return True

        if is_running:
            self.close_steam_graceful()

        self.set_registry_auto_login(target_account)
        self.update_loginusers_vdf(target_account)

        if appid:
            cmd = [self.steam_exe, "-applaunch", str(appid)]
            if launch_args:
                cmd.extend(launch_args.split())
        else:
            cmd = [self.steam_exe]

        subprocess.Popen(cmd)
        return True

    def resolve_pythonw_executable(self) -> str:
        py_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidate = os.path.join(py_dir, "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate

        if hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix:
            base_cand = os.path.join(sys.base_prefix, "pythonw.exe")
            if os.path.isfile(base_cand):
                return base_cand

        which_pyw = shutil.which("pythonw.exe")
        if which_pyw:
            return os.path.abspath(which_pyw)

        return sys.executable

    def create_desktop_shortcut(self, appid, game_name, account_name, persona_name, custom_label=None, target_folder=None, launch_args=""):
        if not win32com:
            raise RuntimeError("pywin32 is required to create shortcuts.")

        shell = win32com.client.Dispatch("WScript.Shell")
        dest_dir = target_folder if target_folder else shell.SpecialFolders("Desktop")
        os.makedirs(dest_dir, exist_ok=True)

        clean_game_name = re.sub(r'[\\/*?:"<>|]', "", game_name).strip()
        clean_user = re.sub(r'[\\/*?:"<>|]', "", persona_name or account_name).strip()

        filename = f"{custom_label}.lnk" if custom_label else f"{clean_game_name} ({clean_user}).lnk"
        shortcut_path = os.path.join(dest_dir, filename)

        icon_path = os.path.join(self.icons_dir, f"{appid}.ico")
        if not os.path.exists(icon_path):
            installed_games = {g["appid"]: g for g in self.get_installed_games()}
            if appid in installed_games and os.path.exists(installed_games[appid]["icon_path"]):
                icon_path = installed_games[appid]["icon_path"]
            else:
                icon_path = self.steam_exe

        sanitized_args = launch_args.replace('"', '\\"') if launch_args else ""

        # Prefer standalone compiled .exe if available
        if getattr(sys, 'frozen', False):
            target_bin = sys.executable
            args_str = f'--appid {appid} --account "{account_name}"'
        elif os.path.exists(self.compiled_exe):
            target_bin = self.compiled_exe
            args_str = f'--appid {appid} --account "{account_name}"'
        else:
            target_bin = self.resolve_pythonw_executable()
            main_py = os.path.join(self.base_dir, "main.py")
            args_str = f'"{main_py}" --appid {appid} --account "{account_name}"'

        if sanitized_args:
            args_str += f' --args "{sanitized_args}"'

        shortcut = shell.CreateShortcut(shortcut_path)
        shortcut.TargetPath = target_bin
        shortcut.Arguments = args_str
        shortcut.WorkingDirectory = self.base_dir
        if os.path.exists(icon_path) and (icon_path.endswith(".ico") or icon_path.endswith(".exe")):
            shortcut.IconLocation = f"{icon_path},0"
        shortcut.Description = f"Avvia {game_name} con account Steam: {persona_name} ({account_name})"
        shortcut.save()

        return shortcut_path

    def create_all_shortcuts_for_account(self, account_name, persona_name, in_subfolder=True):
        shell = win32com.client.Dispatch("WScript.Shell")
        desktop = shell.SpecialFolders("Desktop")
        clean_user = re.sub(r'[\\/*?:"<>|]', "", persona_name or account_name).strip()

        if in_subfolder:
            folder_name = f"Steam - {clean_user}"
            target_dir = os.path.join(desktop, folder_name)
            os.makedirs(target_dir, exist_ok=True)
        else:
            target_dir = desktop

        created = []
        for g in self.get_installed_games():
            appid = g["appid"]
            gname = g["name"]
            l_args = self.get_game_launch_options(appid, account_name)
            custom_lbl = gname if in_subfolder else f"{gname} ({clean_user})"
            sc = self.create_desktop_shortcut(appid, gname, account_name, persona_name,
                                              custom_label=custom_lbl,
                                              target_folder=target_dir,
                                              launch_args=l_args)
            created.append(sc)
        return target_dir, created

    def get_existing_smart_shortcuts(self):
        if not win32com:
            return []

        shell = win32com.client.Dispatch("WScript.Shell")
        desktop = shell.SpecialFolders("Desktop")

        results = []
        scan_folders = [desktop]
        for item in glob.glob(os.path.join(desktop, "Steam - *")):
            if os.path.isdir(item):
                scan_folders.append(item)

        for folder in scan_folders:
            for file in glob.glob(os.path.join(folder, "*.lnk")):
                try:
                    sc = shell.CreateShortcut(file)
                    args = sc.Arguments.lower()
                    target = sc.TargetPath.lower()
                    if "--account" in args and ("steamsmartswitcher" in target or "launcher.py" in args or "main.py" in args):
                        appid_m = re.search(r'--appid\s+(\d+)', sc.Arguments)
                        acc_m = re.search(r'--account\s+"?([^"\s]+)"?', sc.Arguments)
                        launch_m = re.search(r'--args\s+"([^"]+)"', sc.Arguments)
                        results.append({
                            "filename": os.path.basename(file),
                            "folder": os.path.basename(folder) if folder != desktop else "Desktop",
                            "path": file,
                            "appid": appid_m.group(1) if appid_m else "?",
                            "account": acc_m.group(1) if acc_m else "?",
                            "launch_args": launch_m.group(1) if launch_m else "",
                            "description": sc.Description
                        })
                except Exception:
                    pass
        return results

    def is_windows_autostart_enabled(self):
        run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "SteamSmartSwitcher")
                return True, val
        except Exception:
            return False, ""

    def set_windows_autostart(self, enabled=True, start_minimized=True):
        run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    if getattr(sys, 'frozen', False):
                        cmd = f'"{sys.executable}"'
                    elif os.path.exists(self.compiled_exe):
                        cmd = f'"{self.compiled_exe}"'
                    else:
                        main_py = os.path.join(self.base_dir, "main.py")
                        pythonw_path = self.resolve_pythonw_executable()
                        cmd = f'"{pythonw_path}" "{main_py}"'
                    
                    if start_minimized:
                        cmd += " --minimized"
                    winreg.SetValueEx(key, "SteamSmartSwitcher", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "SteamSmartSwitcher")
                    except FileNotFoundError:
                        pass
            self.settings["autostart_windows"] = enabled
            self.save_settings()
            return True
        except Exception as e:
            print(f"Error setting Windows autostart: {e}")
            return False

    def apply_boot_default_account(self):
        def_acc = self.settings.get("default_account_on_boot", "").strip()
        if def_acc:
            cur_acc = self.get_current_auto_login_user().lower()
            if cur_acc != def_acc.lower():
                self.set_registry_auto_login(def_acc)
                self.update_loginusers_vdf(def_acc)

    def get_account_tag(self, account_name):
        return self.settings.get("account_tags", {}).get(account_name.lower(), "")

    def set_account_tag(self, account_name, tag):
        if "account_tags" not in self.settings:
            self.settings["account_tags"] = {}
        self.settings["account_tags"][account_name.lower()] = tag.strip()
        self.save_settings()

    def get_game_launch_options(self, appid, account_name=""):
        key = f"{appid}@{account_name.lower()}" if account_name else str(appid)
        return self.settings.get("launch_options", {}).get(key, self.settings.get("launch_options", {}).get(str(appid), ""))

    def set_game_launch_options(self, appid, options, account_name=""):
        if "launch_options" not in self.settings:
            self.settings["launch_options"] = {}
        key = f"{appid}@{account_name.lower()}" if account_name else str(appid)
        self.settings["launch_options"][key] = options.strip()
        self.save_settings()

    def get_remembered_accounts(self):
        loginusers_path = os.path.join(self.steam_path, "config", "loginusers.vdf")
        accounts = []
        if not os.path.exists(loginusers_path):
            return accounts

        try:
            with open(loginusers_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            current_auto_user = self.get_current_auto_login_user().lower()

            user_blocks = re.findall(r'"(\d{17})"\s*\{([^}]+)\}', text)
            for steamid, block in user_blocks:
                acc_name_m = re.search(r'"AccountName"\s*"([^"]+)"', block)
                persona_name_m = re.search(r'"PersonaName"\s*"([^"]+)"', block)
                remember_m = re.search(r'"RememberPassword"\s*"([^"]+)"', block)
                auto_login_m = re.search(r'"AutoLogin"\s*"([^"]+)"', block, re.IGNORECASE)
                most_recent_m = re.search(r'"mostrecent"\s*"([^"]+)"', block, re.IGNORECASE)
                timestamp_m = re.search(r'"Timestamp"\s*"([^"]+)"', block)

                acc_name = acc_name_m.group(1).strip() if acc_name_m else ""
                persona_name = persona_name_m.group(1).strip() if persona_name_m else acc_name

                if not acc_name:
                    continue

                is_active = (acc_name.lower() == current_auto_user)
                tag = self.get_account_tag(acc_name)

                accounts.append({
                    "steamid": steamid,
                    "account_name": acc_name,
                    "persona_name": persona_name,
                    "remember_password": remember_m.group(1) if remember_m else "1",
                    "auto_login": auto_login_m.group(1) if auto_login_m else "0",
                    "most_recent": most_recent_m.group(1) if most_recent_m else "0",
                    "timestamp": int(timestamp_m.group(1)) if timestamp_m else 0,
                    "is_active": is_active,
                    "tag": tag,
                    "avatar_path": self.get_cached_avatar_path(steamid)
                })
        except Exception as e:
            print(f"Error parsing loginusers.vdf: {e}")

        accounts.sort(key=lambda x: (not x["is_active"], -x["timestamp"]))
        return accounts

    def get_cached_avatar_path(self, steamid):
        p = os.path.join(self.avatars_dir, f"{steamid}.png")
        return p if os.path.exists(p) else None

    def fetch_and_cache_avatar(self, steamid, persona_name=""):
        cached = os.path.join(self.avatars_dir, f"{steamid}.png")
        if os.path.exists(cached):
            return cached

        local_avatar = os.path.join(self.steam_path, "config", "avatars", f"{steamid}.png")
        if os.path.exists(local_avatar):
            try:
                img = Image.open(local_avatar)
                img.save(cached, format="PNG")
                return cached
            except Exception:
                pass

        url = f"https://steamcommunity.com/profiles/{steamid}/?xml=1"
        try:
            r = requests.get(url, timeout=4)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                avatar_node = root.find("avatarMedium") or root.find("avatarFull") or root.find("avatarIcon")
                if avatar_node is not None and avatar_node.text:
                    img_resp = requests.get(avatar_node.text, timeout=5)
                    if img_resp.status_code == 200:
                        img = Image.open(io.BytesIO(img_resp.content))
                        img = img.resize((64, 64), Image.Resampling.LANCZOS)
                        img.save(cached, format="PNG")
                        return cached
        except Exception as e:
            print(f"Failed to fetch avatar for {steamid}: {e}")

        return self._generate_fallback_avatar(steamid, persona_name)

    def _generate_fallback_avatar(self, steamid, persona_name):
        cached = os.path.join(self.avatars_dir, f"{steamid}.png")
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
                paths = re.findall(r'"path"\s*"([^"]+)"', content)
                for p in paths:
                    norm_p = os.path.normpath(p.replace("\\\\", "\\"))
                    if os.path.exists(norm_p) and not any(os.path.samefile(norm_p, f) for f in folders):
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

    def get_installed_games(self):
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
                        last_owner_id = last_owner_m.group(1).strip() if last_owner_m else ""

                        if appid in exclude_appids or appid in seen_appids:
                            continue
                        seen_appids.add(appid)

                        if size_bytes > 1024**3:
                            size_str = f"{size_bytes / (1024**3):.1f} GB"
                        elif size_bytes > 1024**2:
                            size_str = f"{size_bytes / (1024**2):.0f} MB"
                        else:
                            size_str = f"{size_bytes} B"

                        last_played_str = datetime.datetime.fromtimestamp(last_played_ts).strftime("%d/%m/%Y %H:%M") if last_played_ts > 0 else "Mai avviato"

                        full_dir = os.path.join(lib, "steamapps", "common", installdir) if installdir else ""
                        icon_path = self.resolve_game_icon(appid, name, installdir, lib, url_icons)
                        poster_path = self.get_cached_poster_path(appid)
                        capsule_path = self.get_cached_capsule_path(appid)
                        drive = os.path.splitdrive(lib)[0] or "C:"

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

    def resolve_game_icon(self, appid, name, installdir, library_path, url_icons=None):
        custom_icon = os.path.join(self.icons_dir, f"{appid}.ico")
        if os.path.exists(custom_icon):
            return custom_icon

        if url_icons and appid in url_icons and os.path.exists(url_icons[appid]):
            return url_icons[appid]

        if installdir and library_path:
            game_folder = os.path.join(library_path, "steamapps", "common", installdir)
            if os.path.exists(game_folder):
                icos = glob.glob(os.path.join(game_folder, "*.ico"))
                if icos:
                    return icos[0]
                exes = glob.glob(os.path.join(game_folder, "*.exe"))
                if exes:
                    return exes[0]

        steam_games_ico = os.path.join(self.steam_path, "steam", "games")
        if os.path.exists(steam_games_ico):
            icos = [os.path.join(steam_games_ico, f) for f in os.listdir(steam_games_ico) if f.endswith(".ico") and f != "SteamMovie.ico"]
            if icos:
                return icos[0]

        return self.steam_exe

    def get_cached_poster_path(self, appid):
        p = os.path.join(self.posters_dir, f"{appid}.jpg")
        return p if os.path.exists(p) else None

    def get_cached_capsule_path(self, appid):
        p = os.path.join(self.capsules_dir, f"{appid}.jpg")
        return p if os.path.exists(p) else None

    def fetch_and_cache_game_images(self, appid, name=""):
        poster_path = os.path.join(self.posters_dir, f"{appid}.jpg")
        capsule_path = os.path.join(self.capsules_dir, f"{appid}.jpg")

        headers = {"User-Agent": "Mozilla/5.0"}
        if not os.path.exists(poster_path):
            urls = [
                f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg",
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
            ]
            for u in urls:
                try:
                    r = requests.get(u, headers=headers, timeout=4)
                    if r.status_code == 200:
                        with open(poster_path, "wb") as f:
                            f.write(r.content)
                        break
                except Exception:
                    pass

        if not os.path.exists(capsule_path):
            urls = [
                f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
            ]
            for u in urls:
                try:
                    r = requests.get(u, headers=headers, timeout=4)
                    if r.status_code == 200:
                        with open(capsule_path, "wb") as f:
                            f.write(r.content)
                        break
                except Exception:
                    pass

        ico_path = os.path.join(self.icons_dir, f"{appid}.ico")
        if not os.path.exists(ico_path):
            src_img = poster_path if os.path.exists(poster_path) else (capsule_path if os.path.exists(capsule_path) else None)
            if src_img:
                try:
                    im = Image.open(src_img)
                    w, h = im.size
                    min_dim = min(w, h)
                    left = (w - min_dim) // 2
                    top = (h - min_dim) // 2
                    cropped = im.crop((left, top, left + min_dim, top + min_dim))
                    resized = cropped.resize((128, 128), Image.Resampling.LANCZOS)
                    resized.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
                except Exception:
                    pass

    def open_game_directory(self, full_dir):
        if full_dir and os.path.exists(full_dir):
            os.startfile(full_dir)
            return True
        return False

    def open_store_page(self, appid):
        os.startfile(f"https://store.steampowered.com/app/{appid}")

    def open_community_profile(self, steamid):
        os.startfile(f"https://steamcommunity.com/profiles/{steamid}")
