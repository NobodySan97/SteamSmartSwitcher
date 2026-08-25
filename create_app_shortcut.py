import os
import sys
import win32com.client

def create_manager_shortcut():
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = shell.SpecialFolders("Desktop")
    shortcut_path = os.path.join(desktop, "Steam Smart Switcher.lnk")

    core_dir = r"C:\Users\Admin\SteamSmartLauncher"
    main_py = os.path.join(core_dir, "main.py")
    steam_exe = r"C:\Program Files (x86)\Steam\Steam.exe"

    shortcut = shell.CreateShortcut(shortcut_path)
    shortcut.TargetPath = "pythonw.exe"
    shortcut.Arguments = f'"{main_py}"'
    shortcut.WorkingDirectory = core_dir
    if os.path.exists(steam_exe):
        shortcut.IconLocation = f"{steam_exe},0"
    shortcut.Description = "Gestore account e collegamenti giochi Steam"
    shortcut.save()
    print("Created manager shortcut on Desktop:", shortcut_path)

if __name__ == "__main__":
    create_manager_shortcut()
