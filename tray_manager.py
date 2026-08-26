import os
import sys
import threading
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu

class TrayManager:
    def __init__(self, core, app):
        self.core = core
        self.app = app
        self.icon = None
        self._is_running = False

    def get_i18n(self):
        if self.app and hasattr(self.app, "i18n"):
            return self.app.i18n
        return lambda k, **kw: k

    def create_tray_image(self):
        """Creates or loads an icon for the system tray."""
        custom_icon = os.path.join(self.core.base_dir, "assets", "icon.png")
        if os.path.exists(custom_icon):
            try:
                img = Image.open(custom_icon)
                return img.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception:
                pass

        steam_ico = os.path.join(self.core.steam_path, "Steam.exe")
        if os.path.exists(steam_ico):
            try:
                img = Image.open(steam_ico)
                return img.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception:
                pass

        img = Image.new("RGBA", (64, 64), color=(27, 40, 56, 255))
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=(102, 192, 244, 255), outline=(255, 255, 255, 255), width=2)
        d.ellipse((22, 22, 42, 42), fill=(27, 40, 56, 255))
        return img

    def build_menu(self):
        """Dynamically generates tray menu with current accounts and games."""
        _t = self.get_i18n()
        accounts = self.core.get_remembered_accounts()
        games = self.core.get_installed_games()
        active_user = self.core.get_current_auto_login_user()

        active_acc_obj = next((a for a in accounts if a["account_name"].lower() == active_user.lower()), None)
        if active_acc_obj:
            active_display = f"{_t('active_account_prefix')}{active_acc_obj['persona_name']} ({active_acc_obj['account_name']})"
        elif active_user:
            active_display = f"{_t('active_account_prefix')}{active_user}"
        else:
            active_display = _t('no_active_account')

        def make_switch_cb(acc_name):
            def cb(icon=None, item_obj=None):
                self._on_switch_account(acc_name)
            return cb

        def make_launch_cb(appid):
            def cb(icon=None, item_obj=None):
                self._on_quick_launch_game(appid)
            return cb

        account_items = []
        for acc in accounts:
            acc_name = acc["account_name"]
            p_name = acc["persona_name"]
            is_cur = (acc_name.lower() == active_user.lower())
            label = f"{'✓ ' if is_cur else '  '}{p_name} ({acc_name})"
            account_items.append(item(label, make_switch_cb(acc_name)))
        
        if not account_items:
            account_items.append(item(_t("no_accounts_found"), lambda icon, item: None, enabled=False))

        game_items = []
        for g in games[:15]:
            appid = g["appid"]
            gname = g["name"]
            game_items.append(item(gname, make_launch_cb(appid)))

        if not game_items:
            game_items.append(item(_t("no_games_found"), lambda icon, item: None, enabled=False))

        def on_show(icon=None, item_obj=None):
            self._on_show_app()

        def on_open_desk(icon=None, item_obj=None):
            self._on_open_desktop()

        def on_exit(icon=None, item_obj=None):
            self._on_quit()

        menu_items = [
            item(active_display, lambda icon, item: None, enabled=False),
            Menu.SEPARATOR,
            item(f"👤 {_t('accounts_section_title')}", Menu(*account_items)),
            item(f"🎮 {_t('games_section_title')}", Menu(*game_items)),
            Menu.SEPARATOR,
            item(f"🖥️ {_t('tray_open')}", on_show, default=True),
            item(f"📁 Desktop", on_open_desk),
            Menu.SEPARATOR,
            item(f"❌ {_t('tray_exit')}", on_exit)
        ]
        return Menu(*menu_items)

    def _on_switch_account(self, account_name):
        def _worker():
            try:
                from main import WindowsNamedMutex
                with WindowsNamedMutex("Local\\SteamSmartLauncher_Switch_Lock", timeout_ms=15000):
                    self.core.switch_account_and_launch(account_name, appid=None)
                if self.app and hasattr(self.app, "root") and getattr(self.app, "_is_running", False):
                    self.app.root.after(1500, self.app.refresh_data)
                self.update_menu()
            except Exception as ex:
                if self.icon:
                    try:
                        self.icon.notify(str(ex), "Steam Smart Switcher")
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_quick_launch_game(self, appid):
        def _worker():
            try:
                from main import WindowsNamedMutex
                with WindowsNamedMutex("Local\\SteamSmartLauncher_Switch_Lock", timeout_ms=15000):
                    active_user = self.core.get_current_auto_login_user()
                    l_args = self.core.get_game_launch_options(appid, active_user)
                    self.core.switch_account_and_launch(active_user, appid, l_args)
            except Exception as ex:
                if self.icon:
                    try:
                        self.icon.notify(str(ex), "Steam Smart Switcher")
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_show_app(self):
        if self.app and hasattr(self.app, "root"):
            self.app.root.after(0, self.app.show_window)

    def _on_open_desktop(self):
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        os.startfile(desktop)

    def _on_quit(self):
        self.stop()
        if self.app and hasattr(self.app, "root"):
            self.app.root.after(0, self.app.quit_completely)

    def update_menu(self):
        if self.icon and self._is_running:
            try:
                self.icon.menu = self.build_menu()
            except Exception:
                pass

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        tray_img = self.create_tray_image()
        self.icon = pystray.Icon("steam_smart_switcher", tray_img, "Steam Smart Switcher", menu=self.build_menu())

        def run_tray():
            try:
                self.icon.run()
            except Exception as e:
                print(f"Tray icon error: {e}")

        t = threading.Thread(target=run_tray, daemon=True)
        t.start()

    def stop(self):
        self._is_running = False
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
