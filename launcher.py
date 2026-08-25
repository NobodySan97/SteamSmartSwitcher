import sys
import os
import argparse
import ctypes
from steam_core import SteamCore

WAIT_OBJECT_0 = 0x00000000

class WindowsNamedMutex:
    def __init__(self, name="Global\\SteamSmartLauncher_Switch_Lock", timeout_ms=12000):
        self.name = name
        self.timeout_ms = timeout_ms
        self.handle = None

    def __enter__(self):
        self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            return self
        res = ctypes.windll.kernel32.WaitForSingleObject(self.handle, self.timeout_ms)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handle:
            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None

def main():
    parser = argparse.ArgumentParser(description="Steam Smart Game Launcher")
    parser.add_argument("--appid", type=str, help="Steam App ID of the game to launch")
    parser.add_argument("--account", type=str, required=True, help="Steam account username")
    parser.add_argument("--args", type=str, default="", help="Custom launch arguments")
    
    args = parser.parse_args()

    try:
        with WindowsNamedMutex("Global\\SteamSmartLauncher_Switch_Lock", timeout_ms=15000):
            core = SteamCore()
            core.switch_account_and_launch(target_account=args.account, appid=args.appid, launch_args=args.args)
    except Exception as ex:
        ctypes.windll.user32.MessageBoxW(0, f"Avviso Steam Launcher:\n\n{ex}", "Steam Smart Switcher", 0x30 | 0x0)
        sys.exit(1)

if __name__ == "__main__":
    main()
