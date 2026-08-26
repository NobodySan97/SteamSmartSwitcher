import os
import sys
import json
import time
import subprocess
import threading
import re
import requests

APP_VERSION = "1.1.7"
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
        def parse_ver(v):
            nums = [int(x) for x in re.findall(r'\d+', str(v))]
            while len(nums) < 3:
                nums.append(0)
            return tuple(nums[:3])
        try:
            return parse_ver(latest) > parse_ver(current)
        except Exception:
            return str(latest).strip().lower() != str(current).strip().lower()

    def download_and_apply_update(self, download_url: str, on_progress=None):
        """Downloads new executable in-place, spawns detached PowerShell updater, and restarts."""
        is_frozen = getattr(sys, 'frozen', False)
        if is_frozen:
            target_file = sys.executable
        else:
            target_file = os.path.abspath("SteamSmartSwitcher.exe")

        target_dir = os.path.dirname(target_file)
        update_file = os.path.join(target_dir, "SteamSmartSwitcher_new.exe")

        # Download with stream
        headers = {"User-Agent": "SteamSmartSwitcher-App"}
        try:
            with requests.get(download_url, headers=headers, stream=True, timeout=25) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
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

        curr_pid = os.getpid()
        ps_update_cmd = (
            f"Wait-Process -Id {curr_pid} -Timeout 15 -ErrorAction SilentlyContinue; "
            f"Start-Sleep -Milliseconds 600; "
            f"Move-Item -Path '{update_file}' -Destination '{target_file}' -Force; "
            f"Start-Process -FilePath '{target_file}'"
        )

        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_update_cmd],
                         creationflags=flags)
        os._exit(0)
