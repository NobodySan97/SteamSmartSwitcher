import os
import sys
import json
import time
import subprocess
import threading
import re
import requests

APP_VERSION = "1.2.8"
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

        # Download with adaptive dynamic stream buffer based on real-time network throughput
        headers = {"User-Agent": "SteamSmartSwitcher-App"}
        try:
            with requests.get(download_url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0

                # Adaptive buffer parameters
                current_chunk_size = 262144  # 256 KB probe start
                min_chunk = 65536           # 64 KB minimum
                max_chunk = 16777216        # 16 MB maximum for Gigabit/FTTH fiber

                with open(update_file, "wb") as f:
                    while True:
                        t0 = time.time()
                        chunk = r.raw.read(current_chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        chunk_len = len(chunk)
                        downloaded += chunk_len
                        elapsed = time.time() - t0

                        if on_progress:
                            pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                            on_progress(pct, downloaded, total_size)

                        # Dynamically scale chunk size targeting ~100ms per UI progress tick
                        if elapsed > 0 and chunk_len > 0:
                            speed_bps = chunk_len / elapsed
                            target_chunk = int(speed_bps * 0.1)
                            current_chunk_size = max(min_chunk, min(max_chunk, target_chunk))
        except Exception:
            if os.path.exists(update_file):
                try:
                    os.remove(update_file)
                except Exception:
                    pass
            raise

        # Apply update natively on Windows without PowerShell or external dropper scripts
        bak_file = target_file + ".old"
        if os.path.exists(bak_file):
            try:
                os.remove(bak_file)
            except Exception:
                pass

        try:
            os.rename(target_file, bak_file)
            os.rename(update_file, target_file)
            try:
                subprocess.Popen(["explorer.exe", target_file])
            except Exception:
                os.startfile(target_file)
            time.sleep(0.6)
            os._exit(0)
        except Exception:
            # Fallback for non-frozen environments
            if os.path.exists(update_file):
                try:
                    os.replace(update_file, target_file)
                    try:
                        subprocess.Popen(["explorer.exe", target_file])
                    except Exception:
                        os.startfile(target_file)
                    time.sleep(0.6)
                    os._exit(0)
                except Exception:
                    pass
            raise
