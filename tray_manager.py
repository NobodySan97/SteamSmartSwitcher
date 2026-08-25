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

    def create_tray_image(self):
        """Creates or loads an icon for the system tray."""
        steam_ico = os.path.join(self.core.steam_path, "Steam.exe")
        if os.path.exists(steam_ico):
            try:
                img = Image.open(steam_ico)
                return img.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception:
                pass

        # Fallback icon
        img = Image.new("RGBA", (64, 64), color=(27, 40, 56, 255))
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=(102, 192, 244, 255), outline=(255, 255, 255, 255), width=2)
        d.ellipse((22, 22, 42, 42), fill=(27, 40, 56, 255))
        return img

    def build_menu(self):
        """Dynamically generates tray menu with current accounts and games."""
        accounts = self.core.get_remembered_accounts()
        games = self.core.get_installed_games()
        active_user = self.core.get_current_auto_login_user()

        active_acc_obj = next((a for a in accounts if a["account_name"].lower() == active_user.lower()), None)
        active_display = f"🟢 Attivo: {active_acc_obj['persona_name']} ({active_acc_obj['account_name']})" if active_acc_obj else f"🟢 Attivo: {active_user or 'Nessuno'}"

        # Helper callback creators to satisfy pystray signature
        def make_switch_cb(acc_name):
            def cb(icon=None, item_obj=None):
                self._on_switch_account(acc_name)
            return cb

        def make_launch_cb(appid):
            def cb(icon=None, item_obj=None):
                self._on_quick_launch_game(appid)
            return cb

        # Submenu: Switch Account
        account_items = []
        for acc in accounts:
            acc_name = acc["account_name"]
            p_name = acc["persona_name"]
            is_cur = (acc_name.lower() == active_user.lower())
            label = f"{'✓ ' if is_cur else '  '}{p_name} ({acc_name})"
            account_items.append(item(label, make_switch_cb(acc_name)))
        
        if not account_items:
            account_items.append(item("Nessun account memorizzato", lambda icon, item: None, enabled=False))

        # Submenu: Quick Launch Game
        game_items = []
        for g in games[:15]:
            appid = g["appid"]
            gname = g["name"]
            game_items.append(item(gname, make_launch_cb(appid)))

        if not game_items:
            game_items.append(item("Nessun gioco installato", lambda icon, item: None, enabled=False))

        def on_show(icon=None, item_obj=None):
            self._on_show_app()

        def on_open_desk(icon=None, item_obj=None):
            self._on_open_desktop()

        def on_exit(icon=None, item_obj=None):
            self._on_quit()

        menu_items = [
            item(active_display, lambda icon, item: None, enabled=False),
            Menu.SEPARATOR,
            item("👤 Cambia Account", Menu(*account_items)),
            item("🎮 Avvia Gioco Rapido", Menu(*game_items)),
            Menu.SEPARATOR,
            item("🖥️ Apri Applicazione", on_show, default=True),
            item("📁 Apri Desktop", on_open_desk),
            Menu.SEPARATOR,
            item("❌ Esci", on_exit)
        ]
        return Menu(*menu_items)

    def _on_switch_account(self, account_name):
        self.core.switch_account_and_launch(account_name, appid=None)
        if self.app and hasattr(self.app, "root"):
            self.app.root.after(2000, self.app.refresh_data)
        self.update_menu()

    def _on_quick_launch_game(self, appid):
        active_user = self.core.get_current_auto_login_user()
        l_args = self.core.get_game_launch_options(appid, active_user)
        self.core.switch_account_and_launch(active_user, appid, l_args)

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
