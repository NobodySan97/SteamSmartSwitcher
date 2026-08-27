import sys
import os
import argparse
import ctypes
from steam_core import SteamCore

WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED = 0x00000080
WAIT_TIMEOUT = 0x00000102
ERROR_ACCESS_DENIED = 5

class WindowsNamedMutex:
    def __init__(self, name="SteamSmartLauncher_Switch_Lock", timeout_ms=15000):
        self.primary_name = f"Local\\{name}" if not name.startswith(("Global\\", "Local\\")) else name
        self.fallback_name = f"Local\\{name.split('\\')[-1]}"
        self.timeout_ms = timeout_ms
        self.handle = None
        self.acquired = False

        from ctypes import wintypes
        self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self.k32.CreateMutexW.restype = wintypes.HANDLE
        self.k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k32.WaitForSingleObject.restype = wintypes.DWORD
        self.k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.k32.ReleaseMutex.restype = wintypes.BOOL
        self.k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k32.CloseHandle.restype = wintypes.BOOL

    def __enter__(self):
        self.handle = self.k32.CreateMutexW(None, False, self.primary_name)
        if not self.handle and ctypes.get_last_error() == ERROR_ACCESS_DENIED:
            self.handle = self.k32.CreateMutexW(None, False, self.fallback_name)

        if not self.handle:
            raise RuntimeError(f"Impossibile creare Mutex Windows: WinError {ctypes.get_last_error()}")

        wait_res = self.k32.WaitForSingleObject(self.handle, self.timeout_ms)
        if wait_res in (WAIT_OBJECT_0, WAIT_ABANDONED):
            self.acquired = True
            return self
        elif wait_res == WAIT_TIMEOUT:
            self.k32.CloseHandle(self.handle)
            self.handle = None
            raise TimeoutError("Operazione bloccata: un altro cambio account è attualmente in corso.")
        else:
            self.k32.CloseHandle(self.handle)
            self.handle = None
            raise RuntimeError(f"Attesa Mutex fallita con codice: 0x{wait_res:X}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handle:
            if self.acquired:
                self.k32.ReleaseMutex(self.handle)
                self.acquired = False
            self.k32.CloseHandle(self.handle)
            self.handle = None

def main():
    parser = argparse.ArgumentParser(description="Steam Smart Game Launcher")
    parser.add_argument("--appid", type=str, help="Steam App ID of the game to launch")
    parser.add_argument("--account", type=str, required=True, help="Steam account username")
    parser.add_argument("--args", type=str, default="", help="Custom launch arguments")
    
    args, _ = parser.parse_known_args()

    try:
        with WindowsNamedMutex("Local\\SteamSmartLauncher_Switch_Lock", timeout_ms=15000):
            core = SteamCore()
            core.switch_account_and_launch(target_account=args.account, appid=args.appid, launch_args=args.args, wait_completion=True)
    except Exception as ex:
        ctypes.windll.user32.MessageBoxW(0, f"Avviso Steam Launcher:\n\n{ex}", "Steam Smart Switcher", 0x30 | 0x0)
        sys.exit(1)

if __name__ == "__main__":
    main()
