import os
import sys
import argparse
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import subprocess
import threading
from PIL import Image, ImageTk, ImageDraw

# Enable High-DPI Awareness (Per-Monitor V2 on Windows 10/11)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from steam_core import SteamCore
from tray_manager import TrayManager
from updater import Updater, APP_VERSION, DEFAULT_GITHUB_REPO

# Modern Steam Palette
COLOR_BG = "#171a21"
COLOR_HEADER = "#1b2838"
COLOR_CARD = "#1f2a38"
COLOR_CARD_HOVER = "#2a3d54"
COLOR_CARD_SELECTED = "#2e4868"
COLOR_ACCENT = "#66c0f4"
COLOR_ACCENT_HOVER = "#85d0ff"
COLOR_GREEN = "#5c7e10"
COLOR_GREEN_HOVER = "#739e14"
COLOR_TEXT = "#c7d5e0"
COLOR_TEXT_MUTED = "#8f98a0"
COLOR_BORDER = "#314358"
COLOR_ENTRY_BG = "#10161d"
COLOR_TAG_BG = "#1e374d"
COLOR_OWNED_BG = "#1d3e23"
COLOR_SHARED_BG = "#3e2e1d"

class ToastNotification(tk.Frame):
    def __init__(self, parent, text, icon="✅", duration_ms=2800):
        super().__init__(parent, bg=COLOR_HEADER, highlightthickness=1,
                         highlightbackground=COLOR_ACCENT, padx=16, pady=10)
        lbl = tk.Label(self, text=f"{icon}  {text}", font=("Segoe UI", 10, "bold"),
                       fg="#ffffff", bg=COLOR_HEADER)
        lbl.pack()
        self.place(relx=0.5, rely=0.90, anchor="center")
        self.after(duration_ms, self._fade_out)

    def _fade_out(self):
        self.destroy()

class ModernCard(tk.Frame):
    def __init__(self, parent, on_click=None, **kwargs):
        super().__init__(parent, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, **kwargs)
        self.on_click = on_click
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.is_selected = False

    def _on_enter(self, e):
        if not self.is_selected:
            self.config(bg=COLOR_CARD_HOVER, highlightbackground=COLOR_ACCENT)
            self._propagate_bg(self, COLOR_CARD_HOVER)

    def _on_leave(self, e):
        if not self.is_selected:
            self.config(bg=COLOR_CARD, highlightbackground=COLOR_BORDER)
            self._propagate_bg(self, COLOR_CARD)

    def _on_click(self, e=None):
        if self.on_click:
            self.on_click()

    def _propagate_bg(self, widget, color):
        for child in widget.winfo_children():
            if getattr(child, 'ignore_hover', False) is False:
                if isinstance(child, (tk.Label, tk.Frame)):
                    child.config(bg=color)
                self._propagate_bg(child, color)

    def set_selected(self, selected):
        self.is_selected = selected
        bg = COLOR_CARD_SELECTED if selected else COLOR_CARD
        border = COLOR_ACCENT if selected else COLOR_BORDER
        self.config(bg=bg, highlightbackground=border, highlightthickness=2 if selected else 1)
        self._propagate_bg(self, bg)


class SteamSmartLauncherApp:
    def __init__(self, root, start_minimized=False):
        self.root = root
        self.root.title(f"Steam Smart Account Switcher v{APP_VERSION}")
        self.root.geometry("1160x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=COLOR_BG)

        self.core = SteamCore()
        self.updater = Updater(self.core)
        self.tray = TrayManager(self.core, self)
        self.tray.start()

        self.core.apply_boot_default_account()

        self.selected_account = None
        self.selected_game = None
        self.view_mode = self.core.settings.get("view_mode", "grid")
        self.filter_mode = "all"

        self.accounts = []
        self.games = []
        self.filtered_games = []

        self._search_timer = None
        self.grid_cols = 4

        self.avatar_images = {}
        self.poster_images = {}
        self.capsule_images = {}
        self.icon_images = {}

        self.account_cards = {}
        self.game_cards = {}

        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)
        self._bind_keyboard_shortcuts()

        self._setup_styles()
        self._build_ui()
        self.refresh_data()

        if self.core.settings.get("auto_check_updates", True):
            threading.Thread(target=self._async_check_updates_silent, daemon=True).start()

        if start_minimized or self.core.settings.get("start_minimized", False):
            self.root.withdraw()

    def _bind_keyboard_shortcuts(self):
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<slash>", lambda e: self._focus_search())
        self.root.bind("<Escape>", self._on_escape_pressed)
        self.root.bind("<F5>", lambda e: self.refresh_data())
        self.root.bind("<Control-r>", lambda e: self.refresh_data())
        self.root.bind("<Control-comma>", lambda e: self.open_settings_dialog())
        self.root.bind("<Return>", lambda e: self._on_enter_pressed())

    def _focus_search(self):
        self.entry_search.focus_set()
        self.entry_search.select_range(0, tk.END)
        return "break"

    def _on_escape_pressed(self, event=None):
        if self.entry_search.get():
            self.search_var.set("")
        else:
            self.on_window_close()

    def _on_enter_pressed(self):
        if self.entry_search.focus_get() != self.entry_search and self.selected_game and self.selected_account:
            self.launch_game_now_action()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=COLOR_HEADER,
                        troughcolor=COLOR_BG,
                        bordercolor=COLOR_BORDER,
                        arrowcolor=COLOR_TEXT)
        style.configure("TCombobox",
                        fieldbackground=COLOR_ENTRY_BG,
                        background=COLOR_CARD_HOVER,
                        foreground="#ffffff",
                        darkcolor=COLOR_BORDER,
                        lightcolor=COLOR_BORDER)

    def _build_ui(self):
        # 1. Header Bar
        header_frame = tk.Frame(self.root, bg=COLOR_HEADER, height=75, padx=20, pady=12)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        title_box = tk.Frame(header_frame, bg=COLOR_HEADER)
        title_box.pack(side=tk.LEFT, fill=tk.Y)

        title_line = tk.Frame(title_box, bg=COLOR_HEADER)
        title_line.pack(anchor="w")

        lbl_title = tk.Label(title_line, text="🎮 Steam Smart Switcher", font=("Segoe UI", 16, "bold"), fg=COLOR_ACCENT, bg=COLOR_HEADER)
        lbl_title.pack(side=tk.LEFT)

        lbl_ver = tk.Label(title_line, text=f"v{APP_VERSION}", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, padx=5, pady=1)
        lbl_ver.pack(side=tk.LEFT, padx=(8, 0))

        lbl_subtitle = tk.Label(title_box, text="Switch automatico account Steam, cover grafiche, Family Sharing e gestione rapida",
                                font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_HEADER)
        lbl_subtitle.pack(anchor="w")

        header_right = tk.Frame(header_frame, bg=COLOR_HEADER)
        header_right.pack(side=tk.RIGHT, fill=tk.Y)

        self.avatar_label_header = tk.Label(header_right, bg=COLOR_HEADER)
        self.avatar_label_header.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_active_user = tk.Label(header_right, text="Account Attivo: Inizializzazione...",
                                        font=("Segoe UI", 9, "bold"), fg="#ffffff", bg="#1a3d24",
                                        padx=12, pady=6, relief=tk.FLAT)
        self.lbl_active_user.pack(side=tk.LEFT, padx=(0, 8))

        btn_settings = tk.Button(header_right, text="⚙️ Impostazioni", font=("Segoe UI", 9, "bold"),
                                 fg="#ffffff", bg=COLOR_CARD, activebackground=COLOR_CARD_HOVER,
                                 activeforeground="#ffffff", relief=tk.FLAT, padx=10, pady=5,
                                 cursor="hand2", command=self.open_settings_dialog)
        btn_settings.pack(side=tk.LEFT, padx=(0, 6))

        btn_refresh = tk.Button(header_right, text="🔄 Ricarica (F5)", font=("Segoe UI", 9, "bold"),
                                fg="#ffffff", bg=COLOR_CARD_HOVER, activebackground=COLOR_ACCENT,
                                activeforeground="#ffffff", relief=tk.FLAT, padx=10, pady=5,
                                cursor="hand2", command=self.refresh_data)
        btn_refresh.pack(side=tk.LEFT)

        # 2. Main Content
        content_frame = tk.Frame(self.root, bg=COLOR_BG, padx=16, pady=10)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Left Column: Accounts
        left_col = tk.Frame(content_frame, bg=COLOR_BG, width=420)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        acc_header = tk.Frame(left_col, bg=COLOR_BG)
        acc_header.pack(fill=tk.X, pady=(0, 6))

        lbl_acc_title = tk.Label(acc_header, text="👤 1. Account Rilevati", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg=COLOR_BG)
        lbl_acc_title.pack(side=tk.LEFT)

        self.accounts_container = self._create_scrollable_container(left_col)

        # Right Column: Games
        right_col = tk.Frame(content_frame, bg=COLOR_BG)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        games_top_bar = tk.Frame(right_col, bg=COLOR_BG)
        games_top_bar.pack(fill=tk.X, pady=(0, 6))

        lbl_games_title = tk.Label(games_top_bar, text="🎯 2. Libreria Giochi", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg=COLOR_BG)
        lbl_games_title.pack(side=tk.LEFT)

        self.btn_grid_view = tk.Button(games_top_bar, text="🔲 Griglia Poster", font=("Segoe UI", 8, "bold"),
                                       fg="#ffffff", bg=COLOR_CARD_SELECTED if self.view_mode == "grid" else COLOR_CARD,
                                       relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=lambda: self._set_view_mode("grid"))
        self.btn_grid_view.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_list_view = tk.Button(games_top_bar, text="📋 Lista Dettagli", font=("Segoe UI", 8, "bold"),
                                       fg="#ffffff", bg=COLOR_CARD_SELECTED if self.view_mode == "list" else COLOR_CARD,
                                       relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=lambda: self._set_view_mode("list"))
        self.btn_list_view.pack(side=tk.RIGHT)

        # Filter Chips Row
        self.filter_chips_frame = tk.Frame(right_col, bg=COLOR_BG)
        self.filter_chips_frame.pack(fill=tk.X, pady=(0, 6))

        # Search Bar
        search_frame = tk.Frame(right_col, bg=COLOR_ENTRY_BG, highlightthickness=1, highlightbackground=COLOR_BORDER, pady=2, padx=6)
        search_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_search_icon = tk.Label(search_frame, text="🔍", font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_ENTRY_BG)
        lbl_search_icon.pack(side=tk.LEFT, padx=(2, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_input)
        self.entry_search = tk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 10),
                                     fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, insertbackground=COLOR_ACCENT, relief=tk.FLAT)
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        self.games_scroll_container = tk.Frame(right_col, bg=COLOR_BG)
        self.games_scroll_container.pack(fill=tk.BOTH, expand=True)
        self.games_container = self._create_scrollable_container(self.games_scroll_container)

        # Selected Game Hero Details Panel
        self.game_details_box = tk.Frame(right_col, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, padx=12, pady=10)
        self.game_details_box.pack(fill=tk.X, pady=(8, 0))

        det_top = tk.Frame(self.game_details_box, bg=COLOR_CARD)
        det_top.pack(fill=tk.X)

        self.lbl_selected_game_name = tk.Label(det_top, text="Nessun gioco selezionato", font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=COLOR_CARD)
        self.lbl_selected_game_name.pack(side=tk.LEFT)

        self.lbl_ownership_badge = tk.Label(det_top, text="", font=("Segoe UI", 8, "bold"), fg="#ffffff", bg=COLOR_OWNED_BG, padx=6, pady=1)
        self.lbl_ownership_badge.pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_selected_game_size = tk.Label(det_top, text="", font=("Segoe UI", 9), fg=COLOR_ACCENT, bg=COLOR_CARD)
        self.lbl_selected_game_size.pack(side=tk.RIGHT)

        # Game Stats & Quick Links
        det_links = tk.Frame(self.game_details_box, bg=COLOR_CARD)
        det_links.pack(fill=tk.X, pady=(4, 6))

        self.lbl_last_played = tk.Label(det_links, text="", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        self.lbl_last_played.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_open_folder = tk.Button(det_links, text="📁 File Locali", font=("Segoe UI", 8),
                                         fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, activebackground=COLOR_CARD_HOVER,
                                         relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=self._on_open_game_folder)
        self.btn_open_folder.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_open_store = tk.Button(det_links, text="🛒 Negozio Steam", font=("Segoe UI", 8),
                                        fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, activebackground=COLOR_CARD_HOVER,
                                        relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=self._on_open_store_page)
        self.btn_open_store.pack(side=tk.LEFT)

        launch_opts_row = tk.Frame(self.game_details_box, bg=COLOR_CARD)
        launch_opts_row.pack(fill=tk.X, pady=(4, 0))

        lbl_lopt = tk.Label(launch_opts_row, text="⚙️ Opzioni di Avvio Custom (es. -novid -high):", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        lbl_lopt.pack(side=tk.LEFT)

        self.launch_opts_var = tk.StringVar()
        self.launch_opts_var.trace_add("write", self._on_launch_opts_changed)
        self.entry_launch_opts = tk.Entry(launch_opts_row, textvariable=self.launch_opts_var, font=("Segoe UI", 9),
                                          fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, insertbackground=COLOR_ACCENT,
                                          relief=tk.FLAT, highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.entry_launch_opts.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), ipady=2)

        # 3. Bottom Action Bar
        bottom_bar = tk.Frame(self.root, bg=COLOR_HEADER, padx=20, pady=12, highlightthickness=1, highlightbackground=COLOR_BORDER)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_preview = tk.Label(bottom_bar, text="👈 Seleziona un account e un gioco per iniziare.",
                                    font=("Segoe UI", 10, "bold"), fg=COLOR_ACCENT, bg=COLOR_HEADER)
        self.lbl_preview.pack(anchor="w", pady=(0, 8))

        actions_row = tk.Frame(bottom_bar, bg=COLOR_HEADER)
        actions_row.pack(fill=tk.X)

        self.btn_create_shortcut = tk.Button(actions_row, text="⭐ Crea Icona sul Desktop",
                                             font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=COLOR_ACCENT,
                                             activebackground=COLOR_ACCENT_HOVER, activeforeground="#ffffff",
                                             relief=tk.FLAT, padx=16, pady=8, cursor="hand2",
                                             command=self.create_shortcut_action)
        self.btn_create_shortcut.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_launch_now = tk.Button(actions_row, text="🚀 Avvia Gioco Subito (Enter)",
                                        font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=COLOR_GREEN,
                                        activebackground=COLOR_GREEN_HOVER, activeforeground="#ffffff",
                                        relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                                        command=self.launch_game_now_action)
        self.btn_launch_now.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_create_all_folder = tk.Button(actions_row, text="📂 Genera TUTTI i Giochi per questo Account",
                                               font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_CARD,
                                               activebackground=COLOR_CARD_HOVER, activeforeground="#ffffff",
                                               relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
                                               command=self.create_all_shortcuts_action)
        self.btn_create_all_folder.pack(side=tk.LEFT, padx=(0, 8))

        btn_manage = tk.Button(actions_row, text="📋 Gestione Icone",
                               font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_CARD,
                               activebackground=COLOR_CARD_HOVER, activeforeground="#ffffff",
                               relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
                               command=self.open_manage_shortcuts_dialog)
        btn_manage.pack(side=tk.RIGHT)

        self.lbl_status = tk.Label(self.root, text=f"Pronto  |  Steam Smart Switcher v{APP_VERSION}", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_BG, anchor="w", padx=20, pady=2)
        self.lbl_status.pack(fill=tk.X, side=tk.BOTTOM)

    def _create_scrollable_container(self, parent):
        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLOR_BG)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _configure_canvas_width(event):
            canvas.itemconfig(canvas_window, width=event.width)
            if self.view_mode == "grid":
                cols = max(2, event.width // 140)
                if cols != self.grid_cols:
                    self.grid_cols = cols
                    self._render_games_grid()

        canvas.bind("<Configure>", _configure_canvas_width)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        return scrollable_frame

    def _set_view_mode(self, mode):
        self.view_mode = mode
        self.core.settings["view_mode"] = mode
        self.core.save_settings()

        self.btn_grid_view.config(bg=COLOR_CARD_SELECTED if mode == "grid" else COLOR_CARD)
        self.btn_list_view.config(bg=COLOR_CARD_SELECTED if mode == "list" else COLOR_CARD)
        self._render_games()

    def _set_filter_mode(self, mode):
        self.filter_mode = mode
        self._render_filter_chips()
        self._apply_search_filter()

    def _render_filter_chips(self):
        for w in self.filter_chips_frame.winfo_children():
            w.destroy()

        chips = [
            ("Tutti", "all"),
            ("👑 Di Proprietà", "owned"),
            ("👨‍👩‍👧‍👦 Family Sharing", "shared")
        ]

        for label, mode in chips:
            is_active = (self.filter_mode == mode)
            btn = tk.Button(self.filter_chips_frame, text=label, font=("Segoe UI", 8, "bold" if is_active else "normal"),
                            fg="#ffffff" if is_active else COLOR_TEXT_MUTED,
                            bg=COLOR_CARD_SELECTED if is_active else COLOR_CARD,
                            activebackground=COLOR_CARD_HOVER, relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
                            command=lambda m=mode: self._set_filter_mode(m))
            btn.pack(side=tk.LEFT, padx=(0, 4))

    def show_toast(self, text, icon="✅"):
        ToastNotification(self.root, text, icon=icon)

    def refresh_data(self):
        self.set_status("Rilevamento dati da Steam in corso...")
        active_user = self.core.get_current_auto_login_user()

        self.accounts = self.core.get_remembered_accounts()
        self.games = self.core.get_installed_games()
        self.filtered_games = list(self.games)

        active_acc_obj = next((a for a in self.accounts if a["account_name"].lower() == active_user.lower()), None)
        if active_acc_obj:
            self.lbl_active_user.config(text=f"🟢 Attivo: {active_acc_obj['persona_name']} ({active_acc_obj['account_name']})", bg="#1b4d29")
            self._load_header_avatar(active_acc_obj["steamid"], active_acc_obj["persona_name"])
        elif active_user:
            self.lbl_active_user.config(text=f"🟢 Attivo: {active_user}", bg="#1b4d29")
        else:
            self.lbl_active_user.config(text="⚪ Nessun account attivo", bg="#3d3d3d")

        if not self.selected_account and self.accounts:
            self.selected_account = active_acc_obj if active_acc_obj else self.accounts[0]

        if not self.selected_game and self.games:
            self.selected_game = self.games[0]

        self._render_accounts()
        self._render_filter_chips()
        self._render_games()
        self._update_preview()
        self.tray.update_menu()

        threading.Thread(target=self._async_fetch_assets, daemon=True).start()
        self.set_status(f"Rilevati {len(self.accounts)} account e {len(self.games)} giochi installati.")

    def _async_check_updates_silent(self):
        res = self.updater.check_for_updates()
        if res.get("success") and res.get("has_update"):
            self.root.after(0, lambda: self._show_update_notification_dialog(res))

    def _show_update_notification_dialog(self, info):
        latest = info.get("latest_version")
        dlg = tk.Toplevel(self.root)
        dlg.title("🎉 Aggiornamento Disponibile")
        dlg.geometry("520x380")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_t = tk.Label(dlg, text=f"🚀 Nuova Versione Disponibile: v{latest}", font=("Segoe UI", 13, "bold"), fg=COLOR_ACCENT, bg=COLOR_BG)
        lbl_t.pack(anchor="w", padx=20, pady=(16, 8))

        lbl_sub = tk.Label(dlg, text=f"Versione attuale: v{APP_VERSION}  ➡️  Nuova versione: v{latest}", font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_BG)
        lbl_sub.pack(anchor="w", padx=20, pady=(0, 10))

        box = tk.Frame(dlg, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, padx=12, pady=10)
        box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 12))

        lbl_cl_t = tk.Label(box, text="Novità e Changelog:", font=("Segoe UI", 9, "bold"), fg="#ffffff", bg=COLOR_CARD)
        lbl_cl_t.pack(anchor="w")

        txt_cl = tk.Text(box, height=8, font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, relief=tk.FLAT, highlightthickness=1, highlightbackground=COLOR_BORDER)
        txt_cl.insert(tk.END, info.get("changelog") or "Nessun changelog fornito.")
        txt_cl.config(state=tk.DISABLED)
        txt_cl.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(dlg, variable=progress_var, maximum=100)

        lbl_dl_status = tk.Label(dlg, text="", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_BG)

        btn_row = tk.Frame(dlg, bg=COLOR_BG)
        btn_row.pack(fill=tk.X, padx=20, pady=(0, 16))

        def start_download():
            btn_update.config(state=tk.DISABLED, text="Download in corso...")
            progress_bar.pack(fill=tk.X, padx=20, pady=(0, 4))
            lbl_dl_status.pack(padx=20, pady=(0, 8))

            def on_progress(pct, downloaded, total):
                progress_var.set(pct)
                lbl_dl_status.config(text=f"Scaricamento: {downloaded/(1024*1024):.1f} MB / {total/(1024*1024):.1f} MB ({pct}%)")

            def run():
                try:
                    self.updater.download_and_apply_update(info.get("download_url"), on_progress=on_progress)
                except Exception as ex:
                    dlg.after(0, lambda: messagebox.showerror("Errore Aggiornamento", f"Impossibile applicare l'aggiornamento:\n{ex}"))
                    dlg.after(0, lambda: btn_update.config(state=tk.NORMAL, text="Riprova Aggiornamento"))

            threading.Thread(target=run, daemon=True).start()

        btn_update = tk.Button(btn_row, text="⬇️ Aggiorna Ora", font=("Segoe UI", 10, "bold"),
                               fg="#ffffff", bg=COLOR_GREEN, activebackground=COLOR_GREEN_HOVER,
                               relief=tk.FLAT, padx=14, pady=6, cursor="hand2", command=start_download)
        btn_update.pack(side=tk.LEFT, padx=(0, 8))

        btn_gh = tk.Button(btn_row, text="🌐 Pagina GitHub", font=("Segoe UI", 9),
                           fg=COLOR_TEXT, bg=COLOR_CARD, activebackground=COLOR_CARD_HOVER,
                           relief=tk.FLAT, padx=12, pady=6, cursor="hand2",
                           command=lambda: os.startfile(info.get("release_url") or "https://github.com"))
        btn_gh.pack(side=tk.LEFT)

        btn_skip = tk.Button(btn_row, text="Più Tardi", font=("Segoe UI", 9),
                             fg=COLOR_TEXT_MUTED, bg=COLOR_ENTRY_BG, relief=tk.FLAT,
                             padx=12, pady=6, cursor="hand2", command=dlg.destroy)
        btn_skip.pack(side=tk.RIGHT)

    def _load_header_avatar(self, steamid, persona_name):
        av_path = self.core.get_cached_avatar_path(steamid)
        if av_path and os.path.exists(av_path):
            try:
                img = Image.open(av_path).resize((32, 32), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.avatar_images["header"] = photo
                self.avatar_label_header.config(image=photo)
            except Exception:
                pass

    def _async_fetch_assets(self):
        for acc in self.accounts:
            steamid = acc["steamid"]
            if not self.core.get_cached_avatar_path(steamid):
                self.core.fetch_and_cache_avatar(steamid, acc["persona_name"])
                self.root.after(0, self._render_accounts)

        for g in self.games:
            appid = g["appid"]
            if not self.core.get_cached_poster_path(appid) or not self.core.get_cached_capsule_path(appid):
                self.core.fetch_and_cache_game_images(appid, g["name"])

        self.root.after(0, self._render_games)

    def _render_accounts(self):
        for widget in self.accounts_container.winfo_children():
            widget.destroy()
        self.account_cards.clear()

        if not self.accounts:
            lbl_empty = tk.Label(self.accounts_container, text="Nessun account memorizzato trovato.",
                                 font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_BG, pady=20)
            lbl_empty.pack(anchor="w")
            return

        for acc in self.accounts:
            acc_name = acc["account_name"]
            persona = acc["persona_name"]
            steamid = acc["steamid"]
            is_active = acc["is_active"]
            tag = self.core.get_account_tag(acc_name)

            card = ModernCard(self.accounts_container, on_click=lambda a=acc: self._select_account(a), padx=10, pady=10)
            card.pack(fill=tk.X, pady=4)
            self.account_cards[acc_name] = card

            main_row = tk.Frame(card, bg=COLOR_CARD)
            main_row.pack(fill=tk.X)

            avatar_lbl = tk.Label(main_row, bg=COLOR_CARD)
            avatar_lbl.pack(side=tk.LEFT, padx=(0, 10))

            av_path = self.core.get_cached_avatar_path(steamid)
            if av_path and os.path.exists(av_path):
                try:
                    img = Image.open(av_path).resize((48, 48), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.avatar_images[steamid] = photo
                    avatar_lbl.config(image=photo)
                except Exception:
                    pass
            else:
                avatar_lbl.config(text="👤", font=("Segoe UI", 20), fg=COLOR_ACCENT)

            info_col = tk.Frame(main_row, bg=COLOR_CARD)
            info_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

            top_line = tk.Frame(info_col, bg=COLOR_CARD)
            top_line.pack(fill=tk.X)

            lbl_pname = tk.Label(top_line, text=persona, font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=COLOR_CARD)
            lbl_pname.pack(side=tk.LEFT)

            if is_active:
                lbl_badge = tk.Label(top_line, text="ATTIVO", font=("Segoe UI", 7, "bold"), fg="#ffffff", bg=COLOR_GREEN, padx=5, pady=1)
                lbl_badge.ignore_hover = True
                lbl_badge.pack(side=tk.RIGHT)

            sub_line = tk.Frame(info_col, bg=COLOR_CARD)
            sub_line.pack(fill=tk.X, pady=(2, 2))

            lbl_uname = tk.Label(sub_line, text=f"@{acc_name}", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
            lbl_uname.pack(side=tk.LEFT)

            if tag:
                lbl_tag = tk.Label(sub_line, text=f"🏷️ {tag}", font=("Segoe UI", 8, "bold"), fg=COLOR_ACCENT, bg=COLOR_TAG_BG, padx=4, pady=1)
                lbl_tag.ignore_hover = True
                lbl_tag.pack(side=tk.LEFT, padx=(8, 0))

            btn_row = tk.Frame(card, bg=COLOR_CARD)
            btn_row.pack(fill=tk.X, pady=(6, 0))

            btn_switch = tk.Button(btn_row, text="⚡ Switcha", font=("Segoe UI", 8, "bold"),
                                   fg=COLOR_ACCENT, bg=COLOR_ENTRY_BG, activebackground=COLOR_CARD_HOVER,
                                   relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                   command=lambda a=acc_name: self._switch_only_account(a))
            btn_switch.ignore_hover = True
            btn_switch.pack(side=tk.LEFT, padx=(0, 4))

            btn_tag = tk.Button(btn_row, text="✏️ Tag/Nota", font=("Segoe UI", 8),
                                fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, activebackground=COLOR_CARD_HOVER,
                                relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                command=lambda a=acc_name: self._edit_account_tag(a))
            btn_tag.ignore_hover = True
            btn_tag.pack(side=tk.LEFT, padx=(0, 4))

            btn_profile = tk.Button(btn_row, text="🌐 Profilo", font=("Segoe UI", 8),
                                    fg=COLOR_TEXT, bg=COLOR_ENTRY_BG, activebackground=COLOR_CARD_HOVER,
                                    relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                    command=lambda s=steamid: self.core.open_community_profile(s))
            btn_profile.ignore_hover = True
            btn_profile.pack(side=tk.LEFT)

            if self.selected_account and self.selected_account["account_name"] == acc_name:
                card.set_selected(True)

    def _render_games(self):
        for widget in self.games_container.winfo_children():
            widget.destroy()
        self.game_cards.clear()

        if not self.filtered_games:
            lbl_empty = tk.Label(self.games_container, text="Nessun gioco trovato con questo filtro.", font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_BG, pady=20)
            lbl_empty.pack()
            return

        if self.view_mode == "grid":
            self._render_games_grid()
        else:
            self._render_games_list()

    def _render_games_grid(self):
        grid_frame = tk.Frame(self.games_container, bg=COLOR_BG)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        cols = self.grid_cols
        for i, game in enumerate(self.filtered_games):
            appid = game["appid"]
            name = game["name"]
            poster_path = self.core.get_cached_poster_path(appid)
            owner_info = self.core.get_game_ownership(game, self.selected_account, self.accounts)

            r = i // cols
            c = i % cols

            card = ModernCard(grid_frame, on_click=lambda g=game: self._select_game(g), padx=4, pady=4)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            self.game_cards[appid] = card

            poster_lbl = tk.Label(card, bg=COLOR_CARD)
            poster_lbl.pack(fill=tk.BOTH, expand=True)

            if poster_path and os.path.exists(poster_path):
                try:
                    img = Image.open(poster_path).resize((110, 160), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.poster_images[appid] = photo
                    poster_lbl.config(image=photo)
                except Exception:
                    poster_lbl.config(text="🎮\n" + name[:12], font=("Segoe UI", 9, "bold"), fg=COLOR_ACCENT, width=12, height=8)
            else:
                poster_lbl.config(text="🎮\n" + name[:12], font=("Segoe UI", 9, "bold"), fg=COLOR_ACCENT, width=12, height=8)

            badge_color = COLOR_SHARED_BG if owner_info["is_shared"] else COLOR_OWNED_BG
            badge_txt = "👨‍👩‍👧‍👦 Family" if owner_info["is_shared"] else "👑 Owned"
            lbl_own = tk.Label(card, text=badge_txt, font=("Segoe UI", 7, "bold"), fg="#ffffff", bg=badge_color, padx=4, pady=1)
            lbl_own.pack(pady=(2, 0))

            short_title = name if len(name) <= 15 else name[:14] + "…"
            lbl_t = tk.Label(card, text=short_title, font=("Segoe UI", 8, "bold"), fg="#ffffff", bg=COLOR_CARD)
            lbl_t.pack(pady=(1, 0))

            if self.selected_game and self.selected_game["appid"] == appid:
                card.set_selected(True)

    def _render_games_list(self):
        for game in self.filtered_games:
            appid = game["appid"]
            name = game["name"]
            size_str = game["size_str"]
            drive = game["drive"]
            owner_info = self.core.get_game_ownership(game, self.selected_account, self.accounts)

            card = ModernCard(self.games_container, on_click=lambda g=game: self._select_game(g), padx=12, pady=8)
            card.pack(fill=tk.X, pady=3)
            self.game_cards[appid] = card

            row = tk.Frame(card, bg=COLOR_CARD)
            row.pack(fill=tk.X)

            lbl_gname = tk.Label(row, text=f"🎮  {name}", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=COLOR_CARD)
            lbl_gname.pack(side=tk.LEFT)

            info_box = tk.Frame(row, bg=COLOR_CARD)
            info_box.pack(side=tk.RIGHT)

            badge_color = COLOR_SHARED_BG if owner_info["is_shared"] else COLOR_OWNED_BG
            lbl_own = tk.Label(info_box, text=owner_info["badge_text"], font=("Segoe UI", 8, "bold"), fg="#ffffff", bg=badge_color, padx=6, pady=2)
            lbl_own.pack(side=tk.LEFT, padx=(0, 6))

            lbl_size = tk.Label(info_box, text=f"💾 {size_str} ({drive})", font=("Segoe UI", 8), fg=COLOR_ACCENT, bg=COLOR_ENTRY_BG, padx=6, pady=2)
            lbl_size.pack(side=tk.LEFT, padx=(0, 6))

            lbl_appid = tk.Label(info_box, text=f"ID: {appid}", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_ENTRY_BG, padx=6, pady=2)
            lbl_appid.pack(side=tk.LEFT)

            if self.selected_game and self.selected_game["appid"] == appid:
                card.set_selected(True)

    def _on_search_input(self, *args):
        if self._search_timer:
            self.root.after_cancel(self._search_timer)
        self._search_timer = self.root.after(180, self._apply_search_filter)

    def _apply_search_filter(self):
        query = self.search_var.get().strip().lower()
        res = list(self.games)

        if self.filter_mode == "owned":
            res = [g for g in res if self.core.get_game_ownership(g, self.selected_account, self.accounts)["is_owner"]]
        elif self.filter_mode == "shared":
            res = [g for g in res if self.core.get_game_ownership(g, self.selected_account, self.accounts)["is_shared"]]

        if query:
            res = [g for g in res if query in g["name"].lower() or query in g["appid"]]

        self.filtered_games = res
        self._render_games()

    def _select_account(self, acc):
        self.selected_account = acc
        for acc_name, card in self.account_cards.items():
            card.set_selected(acc_name == acc["account_name"])
        self._render_games()
        self._update_preview()

    def _select_game(self, game):
        self.selected_game = game
        for appid, card in self.game_cards.items():
            card.set_selected(appid == game["appid"])
        self._update_preview()

    def _update_preview(self):
        if self.selected_game:
            g = self.selected_game
            owner_info = self.core.get_game_ownership(g, self.selected_account, self.accounts)

            self.lbl_selected_game_name.config(text=f"🎮 {g['name']} (ID: {g['appid']})")
            self.lbl_ownership_badge.config(
                text=owner_info["badge_text"],
                bg=COLOR_SHARED_BG if owner_info["is_shared"] else COLOR_OWNED_BG
            )
            self.lbl_selected_game_size.config(text=f"Spazio: {g.get('size_str', 'N/D')} su {g.get('drive', 'C:')}")
            self.lbl_last_played.config(text=f"⏱️ Ultima sessione: {g.get('last_played_str', 'Mai')}")

            acc_name = self.selected_account["account_name"] if self.selected_account else ""
            opts = self.core.get_game_launch_options(g["appid"], acc_name)
            self.launch_opts_var.set(opts)
        else:
            self.lbl_selected_game_name.config(text="Nessun gioco selezionato")
            self.lbl_ownership_badge.config(text="")
            self.lbl_selected_game_size.config(text="")
            self.lbl_last_played.config(text="")

        if self.selected_game and self.selected_account:
            g_name = self.selected_game["name"]
            p_name = self.selected_account["persona_name"]
            u_name = self.selected_account["account_name"]
            l_opts = self.launch_opts_var.get().strip()
            opts_str = f" | Opzioni: '{l_opts}'" if l_opts else ""
            self.lbl_preview.config(text=f"🎯 Configurazione:  [ {g_name} ]  ➡️  Account: [ {p_name} ({u_name}) ]{opts_str}")
            self.btn_create_shortcut.config(state=tk.NORMAL)
            self.btn_launch_now.config(state=tk.NORMAL)
            self.btn_create_all_folder.config(state=tk.NORMAL)
        else:
            self.lbl_preview.config(text="👈 Seleziona sia un account che un gioco.")
            self.btn_create_shortcut.config(state=tk.DISABLED)
            self.btn_launch_now.config(state=tk.DISABLED)

    def _on_launch_opts_changed(self, *args):
        if self.selected_game:
            opts = self.launch_opts_var.get().strip()
            acc_name = self.selected_account["account_name"] if self.selected_account else ""
            self.core.set_game_launch_options(self.selected_game["appid"], opts, acc_name)

    def _edit_account_tag(self, account_name):
        current_tag = self.core.get_account_tag(account_name)
        new_tag = simpledialog.askstring("Tag Account", f"Inserisci un'etichetta/nota per @{account_name}\n(es. Principale, Smurf, Co-op, Faceit):", initialvalue=current_tag, parent=self.root)
        if new_tag is not None:
            self.core.set_account_tag(account_name, new_tag)
            self.refresh_data()

    def _switch_only_account(self, account_name):
        is_playing, appid = self.core.is_game_running()
        if is_playing:
            messagebox.showerror("Gioco in Esecuzione", f"Impossibile cambiare account: Un gioco Steam (ID: {appid}) è aperto!\nSalva e chiudi il gioco prima di procedere.")
            return

        res = messagebox.askyesno("Conferma Switch", f"Vuoi passare subito all'account '{account_name}' su Steam?\nSe Steam è aperto, verrà riavviato.")
        if not res:
            return

        self.set_status(f"Passaggio all'account {account_name}...")
        def run():
            try:
                self.core.switch_account_and_launch(account_name, appid=None)
                self.root.after(2000, self.refresh_data)
                self.root.after(0, lambda: self.show_toast(f"Switch a @{account_name} completato!"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Errore Switch", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_open_game_folder(self):
        if self.selected_game and self.selected_game.get("full_dir"):
            self.core.open_game_directory(self.selected_game["full_dir"])
        else:
            messagebox.showinfo("Info", "Cartella del gioco non disponibile.")

    def _on_open_store_page(self):
        if self.selected_game:
            self.core.open_store_page(self.selected_game["appid"])

    def create_shortcut_action(self):
        if not self.selected_game or not self.selected_account:
            return

        appid = self.selected_game["appid"]
        game_name = self.selected_game["name"]
        account_name = self.selected_account["account_name"]
        persona_name = self.selected_account["persona_name"]
        launch_args = self.launch_opts_var.get().strip()

        self.set_status(f"Creazione collegamento per {game_name} ({persona_name})...")
        try:
            shortcut_path = self.core.create_desktop_shortcut(appid, game_name, account_name, persona_name, launch_args=launch_args)
            filename = os.path.basename(shortcut_path)
            self.show_toast(f"Icona creata: {filename}", icon="⭐")
            self.set_status(f"✅ Collegamento creato: {filename}")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile creare il collegamento:\n{e}")

    def create_all_shortcuts_action(self):
        if not self.selected_account:
            return

        account_name = self.selected_account["account_name"]
        persona_name = self.selected_account["persona_name"]

        res = messagebox.askyesno("Genera Tutto", f"Vuoi generare una cartella sul Desktop con TUTTI i tuoi giochi installati ({len(self.games)}) collegati all'account '{persona_name}'?")
        if not res:
            return

        self.set_status(f"Generazione pacchetto giochi per {persona_name}...")
        try:
            target_dir, created = self.core.create_all_shortcuts_for_account(account_name, persona_name, in_subfolder=True)
            folder_name = os.path.basename(target_dir)
            self.show_toast(f"Creata cartella con {len(created)} giochi!", icon="📁")
            os.startfile(target_dir)
            self.set_status(f"✅ Creata cartella '{folder_name}' con {len(created)} scorciatoie!")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante la creazione della cartella:\n{e}")

    def launch_game_now_action(self):
        if not self.selected_game or not self.selected_account:
            return

        is_playing, active_appid = self.core.is_game_running()
        if is_playing and active_appid != int(self.selected_game["appid"]):
            messagebox.showerror("Gioco in Esecuzione", f"Un altro gioco Steam (ID: {active_appid}) è attualmente in esecuzione.\nChiudilo prima di avviare un nuovo gioco.")
            return

        appid = self.selected_game["appid"]
        game_name = self.selected_game["name"]
        account_name = self.selected_account["account_name"]
        persona_name = self.selected_account["persona_name"]
        launch_args = self.launch_opts_var.get().strip()

        self.set_status(f"Avvio di {game_name} con account {persona_name}...")
        def run():
            try:
                self.core.switch_account_and_launch(account_name, appid, launch_args=launch_args)
                self.root.after(3000, self.refresh_data)
                self.root.after(0, lambda: self.show_toast(f"Avvio {game_name} ({persona_name})...", icon="🚀"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Errore Avvio", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def open_manage_shortcuts_dialog(self):
        shortcuts = self.core.get_existing_smart_shortcuts()

        dlg = tk.Toplevel(self.root)
        dlg.title("Collegamenti Smart Rilevati")
        dlg.geometry("640x480")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_dlg_title = tk.Label(dlg, text="📋 Collegamenti Smart sul Desktop e Cartelle", font=("Segoe UI", 12, "bold"), fg=COLOR_ACCENT, bg=COLOR_BG)
        lbl_dlg_title.pack(anchor="w", padx=16, pady=(16, 8))

        box = tk.Frame(dlg, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        box.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        container = self._create_scrollable_container(box)

        if not shortcuts:
            lbl_none = tk.Label(container, text="Nessun collegamento smart trovato sul Desktop.", font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_BG, pady=20)
            lbl_none.pack()
        else:
            for sc in shortcuts:
                item = tk.Frame(container, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, padx=10, pady=8)
                item.pack(fill=tk.X, pady=3, padx=4)

                row1 = tk.Frame(item, bg=COLOR_CARD)
                row1.pack(fill=tk.X)

                lbl_fn = tk.Label(row1, text=f"[{sc['folder']}]  {sc['filename']}", font=("Segoe UI", 9, "bold"), fg="#ffffff", bg=COLOR_CARD)
                lbl_fn.pack(side=tk.LEFT)

                def delete_sc(path=sc["path"], row_widget=item):
                    if messagebox.askyesno("Elimina", f"Vuoi eliminare il collegamento:\n{os.path.basename(path)}?"):
                        try:
                            os.remove(path)
                            row_widget.destroy()
                            self.show_toast("Collegamento rimosso.", icon="🗑️")
                        except Exception as ex:
                            messagebox.showerror("Errore", f"Impossibile eliminare: {ex}")

                btn_del = tk.Button(row1, text="🗑️ Elimina", font=("Segoe UI", 8), fg="#ff5555", bg=COLOR_ENTRY_BG,
                                    relief=tk.FLAT, padx=6, pady=2, cursor="hand2", command=delete_sc)
                btn_del.pack(side=tk.RIGHT)

                lbl_sub = tk.Label(item, text=f"AppID: {sc['appid']}  |  Account: {sc['account']}  |  Parametri: '{sc['launch_args'] or 'Nessuno'}'",
                                   font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
                lbl_sub.pack(anchor="w", pady=(2, 0))

        btn_close = tk.Button(dlg, text="Chiudi", font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_CARD_HOVER,
                              relief=tk.FLAT, padx=16, pady=6, cursor="hand2", command=dlg.destroy)
        btn_close.pack(pady=(0, 14))

    def open_settings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Impostazioni & Preferenze")
        dlg.geometry("560x540")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_title = tk.Label(dlg, text="⚙️ Impostazioni Generali", font=("Segoe UI", 13, "bold"), fg=COLOR_ACCENT, bg=COLOR_BG)
        lbl_title.pack(anchor="w", padx=20, pady=(16, 12))

        box = tk.Frame(dlg, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, padx=16, pady=16)
        box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 16))

        is_autostart, _ = self.core.is_windows_autostart_enabled()
        var_autostart = tk.BooleanVar(value=is_autostart)
        var_start_minimized = tk.BooleanVar(value=self.core.settings.get("start_minimized", False))
        var_close_to_tray = tk.BooleanVar(value=self.core.settings.get("close_to_tray", True))
        var_notifications = tk.BooleanVar(value=self.core.settings.get("show_notifications", True))
        var_auto_update = tk.BooleanVar(value=self.core.settings.get("auto_check_updates", True))

        cb_autostart = tk.Checkbutton(box, text="🚀 Avvia automaticamente con Windows all'accensione del PC",
                                      variable=var_autostart, font=("Segoe UI", 9), fg="#ffffff", bg=COLOR_CARD,
                                      selectcolor=COLOR_ENTRY_BG, activebackground=COLOR_CARD, activeforeground="#ffffff")
        cb_autostart.pack(anchor="w", pady=4)

        cb_min = tk.Checkbutton(box, text="📥 Avvia direttamente nella barra (Minimizzato nel System Tray)",
                                variable=var_start_minimized, font=("Segoe UI", 9), fg="#ffffff", bg=COLOR_CARD,
                                selectcolor=COLOR_ENTRY_BG, activebackground=COLOR_CARD, activeforeground="#ffffff")
        cb_min.pack(anchor="w", pady=4)

        cb_close = tk.Checkbutton(box, text="🔲 Riduci a icona nel System Tray quando si preme [X]",
                                  variable=var_close_to_tray, font=("Segoe UI", 9), fg="#ffffff", bg=COLOR_CARD,
                                  selectcolor=COLOR_ENTRY_BG, activebackground=COLOR_CARD, activeforeground="#ffffff")
        cb_close.pack(anchor="w", pady=4)

        cb_notif = tk.Checkbutton(box, text="🔔 Mostra notifiche di Windows al cambio account o avvio",
                                  variable=var_notifications, font=("Segoe UI", 9), fg="#ffffff", bg=COLOR_CARD,
                                  selectcolor=COLOR_ENTRY_BG, activebackground=COLOR_CARD, activeforeground="#ffffff")
        cb_notif.pack(anchor="w", pady=4)

        cb_upd = tk.Checkbutton(box, text="🔄 Controlla automaticamente aggiornamenti da GitHub all'avvio",
                                variable=var_auto_update, font=("Segoe UI", 9), fg="#ffffff", bg=COLOR_CARD,
                                selectcolor=COLOR_ENTRY_BG, activebackground=COLOR_CARD, activeforeground="#ffffff")
        cb_upd.pack(anchor="w", pady=4)

        tk.Frame(box, bg=COLOR_BORDER, height=1).pack(fill=tk.X, pady=8)

        lbl_def = tk.Label(box, text="👤 Account Predefinito all'Avvio di Windows:", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_CARD)
        lbl_def.pack(anchor="w")

        account_options = ["(Nessuno - Lascia l'ultimo usato)"] + [f"{a['persona_name']} (@{a['account_name']})" for a in self.accounts]
        account_usernames = [""] + [a["account_name"] for a in self.accounts]

        cur_def = self.core.settings.get("default_account_on_boot", "")
        cur_idx = 0
        if cur_def:
            for i, u in enumerate(account_usernames):
                if u.lower() == cur_def.lower():
                    cur_idx = i
                    break

        combo_def = ttk.Combobox(box, values=account_options, state="readonly", font=("Segoe UI", 9))
        combo_def.current(cur_idx)
        combo_def.pack(fill=tk.X, pady=(4, 8))

        # GitHub Repo & Manual Update Check
        lbl_repo = tk.Label(box, text="🌐 Repository GitHub (owner/repo):", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_CARD)
        lbl_repo.pack(anchor="w")

        repo_frame = tk.Frame(box, bg=COLOR_CARD)
        repo_frame.pack(fill=tk.X, pady=(4, 0))

        var_repo = tk.StringVar(value=self.core.settings.get("github_repo", DEFAULT_GITHUB_REPO))
        entry_repo = tk.Entry(repo_frame, textvariable=var_repo, font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_ENTRY_BG,
                              insertbackground=COLOR_ACCENT, relief=tk.FLAT, highlightthickness=1, highlightbackground=COLOR_BORDER)
        entry_repo.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        def manual_check():
            self.core.settings["github_repo"] = var_repo.get().strip()
            self.core.save_settings()
            btn_chk.config(state=tk.DISABLED, text="Verifica...")
            def run():
                res = self.updater.check_for_updates()
                dlg.after(0, lambda: btn_chk.config(state=tk.NORMAL, text="🔍 Controlla"))
                if res.get("success"):
                    if res.get("has_update"):
                        dlg.after(0, lambda: self._show_update_notification_dialog(res))
                    else:
                        dlg.after(0, lambda: messagebox.showinfo("Nessun Aggiornamento", f"Stai già utilizzando l'ultima versione disponibile (v{APP_VERSION})."))
                else:
                    dlg.after(0, lambda: messagebox.showwarning("Controllo Aggiornamenti", res.get("error", "Errore sconosciuto.")))
            threading.Thread(target=run, daemon=True).start()

        btn_chk = tk.Button(repo_frame, text="🔍 Controlla", font=("Segoe UI", 8, "bold"),
                            fg="#ffffff", bg=COLOR_CARD_HOVER, activebackground=COLOR_ACCENT,
                            relief=tk.FLAT, padx=10, pady=3, cursor="hand2", command=manual_check)
        btn_chk.pack(side=tk.RIGHT, padx=(6, 0))

        def save_and_close():
            self.core.settings["start_minimized"] = var_start_minimized.get()
            self.core.settings["close_to_tray"] = var_close_to_tray.get()
            self.core.settings["show_notifications"] = var_notifications.get()
            self.core.settings["auto_check_updates"] = var_auto_update.get()
            self.core.settings["github_repo"] = var_repo.get().strip()

            autostart_val = var_autostart.get()
            self.core.set_windows_autostart(autostart_val, start_minimized=var_start_minimized.get())

            selected_acc_idx = combo_def.current()
            if selected_acc_idx > 0 and selected_acc_idx < len(account_usernames):
                self.core.settings["default_account_on_boot"] = account_usernames[selected_acc_idx]
            else:
                self.core.settings["default_account_on_boot"] = ""

            self.core.save_settings()
            self.show_toast("Impostazioni salvate!")
            dlg.destroy()

        btn_save = tk.Button(dlg, text="💾 Salva Impostazioni", font=("Segoe UI", 10, "bold"),
                             fg="#ffffff", bg=COLOR_GREEN, activebackground=COLOR_GREEN_HOVER,
                             relief=tk.FLAT, padx=16, pady=6, cursor="hand2", command=save_and_close)
        btn_save.pack(pady=(0, 16))

    def on_window_close(self):
        if self.core.settings.get("close_to_tray", True):
            self.root.withdraw()
            if self.core.settings.get("show_notifications", True) and self.tray and self.tray.icon:
                try:
                    self.tray.icon.notify("L'applicazione è attiva nella barra delle applicazioni.", "Steam Smart Switcher")
                except Exception:
                    pass
        else:
            self.quit_completely()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_completely(self):
        if self.tray:
            self.tray.stop()
        self.root.destroy()
        sys.exit(0)

    def set_status(self, text):
        self.lbl_status.config(text=text)

class WindowsNamedMutex:
    def __init__(self, name="Global\\SteamSmartLauncher_Switch_Lock", timeout_ms=12000):
        self.name = name
        self.timeout_ms = timeout_ms
        self.handle = None

    def __enter__(self):
        self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            return self
        ctypes.windll.kernel32.WaitForSingleObject(self.handle, self.timeout_ms)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handle:
            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None

def main():
    parser = argparse.ArgumentParser(description="Steam Smart Switcher & Game Launcher")
    parser.add_argument("--minimized", "--tray", action="store_true", help="Start directly minimized in system tray")
    parser.add_argument("--appid", type=str, help="Steam App ID of the game to launch")
    parser.add_argument("--account", type=str, help="Steam account username")
    parser.add_argument("--args", type=str, default="", help="Custom launch arguments")
    args, _ = parser.parse_known_args()

    # DUAL MODE: If --account is passed, run headless launcher mode!
    if args.account:
        try:
            with WindowsNamedMutex("Global\\SteamSmartLauncher_Switch_Lock", timeout_ms=15000):
                core = SteamCore()
                core.switch_account_and_launch(target_account=args.account, appid=args.appid, launch_args=args.args)
        except Exception as ex:
            ctypes.windll.user32.MessageBoxW(0, f"Avviso Steam Launcher:\n\n{ex}", "Steam Smart Switcher", 0x30 | 0x0)
            sys.exit(1)
        sys.exit(0)

    # Standard Mode: Launch GUI
    root = tk.Tk()
    app = SteamSmartLauncherApp(root, start_minimized=args.minimized)
    root.mainloop()

if __name__ == "__main__":
    main()
