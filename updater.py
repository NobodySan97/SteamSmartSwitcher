import os
import sys
import json
import time
import subprocess
import threading
import requests

APP_VERSION = "1.1.4"
DEFAULT_GITHUB_REPO = "NobodySan97/SteamSmartSwitcher"

class Updater:
    def __init__(self, core):
        self.core = core
        self.base_dir = self.core.base_dir
        self.current_version = APP_VERSION

    def get_configured_repo(self):
        return self.core.settings.get("github_repo", DEFAULT_GITHUB_REPO).strip() or DEFAULT_GITHUB_REPO

    def check_for_updates(self):
        repo = self.get_configured_repo()
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        headers = {"User-Agent": f"SteamSmartSwitcher-v{self.current_version}"}

        try:
            r = requests.get(api_url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                tag_name = data.get("tag_name", "").lstrip("v").strip()
                html_url = data.get("html_url", "")
                body = data.get("body", "")
                published_at = data.get("published_at", "")

                download_url = None
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if name.endswith(".exe") and "switcher" in name:
                        download_url = asset.get("browser_download_url")
                        break
                    elif name.endswith(".exe"):
                        download_url = asset.get("browser_download_url")

                has_update = self._is_newer_version(tag_name, self.current_version)

                return {
                    "success": True,
                    "has_update": has_update,
                    "latest_version": tag_name,
                    "current_version": self.current_version,
                    "release_url": html_url,
                    "download_url": download_url,
                    "changelog": body,
                    "published_at": published_at
                }
            elif r.status_code == 404:
                return {"success": False, "error": f"Nessuna release trovata per il repository '{repo}'."}
            else:
                return {"success": False, "error": f"GitHub API ha risposto con codice {r.status_code}."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _is_newer_version(self, latest, current):
        import re
        def parse_ver(v):
            nums = [int(x) for x in re.findall(r'\d+', str(v))]
            while len(nums) < 3:
                nums.append(0)
            return tuple(nums[:3])
        try:
            return parse_ver(latest) > parse_ver(current)
        except Exception:
            return latest.strip().lower() != current.strip().lower()

    def download_and_apply_update(self, download_url, on_progress=None):
        if not download_url:
            raise ValueError("URL di download non valido per la nuova versione.")

        if getattr(sys, 'frozen', False):
            target_file = sys.executable
        else:
            target_file = os.path.join(self.base_dir, "SteamSmartSwitcher.exe")

        target_dir = os.path.dirname(target_file)
        update_file = os.path.join(target_dir, "SteamSmartSwitcher_update.exe")

        # Download with stream and cleanup on failure
        headers = {"User-Agent": f"SteamSmartSwitcher-v{self.current_version}"}
        try:
            with requests.get(download_url, headers=headers, stream=True, timeout=(10, 30)) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                downloaded = 0

                with open(update_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if on_progress:
                                pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                                on_progress(pct, downloaded, total_size)
        except Exception:
            if os.path.exists(update_file):
                try:
                    os.remove(update_file)
                except Exception:
                    pass
            raise

        # Generate atomic batch updater with UTF-8 code page and process cleanup
        updater_bat = os.path.join(target_dir, "_apply_update.bat")
        curr_pid = os.getpid()
        bat_content = f"""@echo off
@chcp 65001 >nul
setlocal
taskkill /F /PID {curr_pid} >nul 2>&1
timeout /t 1 /nobreak >nul
set RETRY_COUNT=0
:RETRY
move /y "{update_file}" "{target_file}" >nul 2>&1
if errorlevel 1 (
    set /a RETRY_COUNT+=1
    if %RETRY_COUNT% GEQ 20 (
        if exist "{update_file}" del /f /q "{update_file}" >nul 2>&1
        (goto) 2>nul & del /f /q "%~f0"
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto RETRY
)
if exist "{update_file}" del /f /q "{update_file}" >nul 2>&1
start "" "{target_file}"
(goto) 2>nul & del /f /q "%~f0"
"""
        with open(updater_bat, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # Launch detached update script and terminate current process immediately
        flags = 0
        if os.name == 'nt':
            flags = subprocess.CREATE_NO_WINDOW | 0x00000008  # DETACHED_PROCESS
        subprocess.Popen(["cmd.exe", "/c", updater_bat], creationflags=flags, close_fds=True)
        os._exit(0)
