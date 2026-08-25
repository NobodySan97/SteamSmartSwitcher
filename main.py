import os
import sys
import gc
import argparse
import ctypes
from ctypes import wintypes
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
from i18n import I18n
from themes import get_theme, THEMES

class ToastNotification(tk.Frame):
    def __init__(self, parent, text, theme, icon="✅", duration_ms=2800):
        super().__init__(parent, bg=theme["header"], highlightthickness=1,
                         highlightbackground=theme["accent"], padx=16, pady=10)
        lbl = tk.Label(self, text=f"{icon}  {text}", font=("Segoe UI", 10, "bold"),
                       fg="#ffffff", bg=theme["header"])
        lbl.pack()
        self.place(relx=0.5, rely=0.90, anchor="center")
        self.after(duration_ms, self._fade_out)

    def _fade_out(self):
        self.destroy()

class ModernCard(tk.Frame):
    def __init__(self, parent, theme, on_click=None, **kwargs):
        self.theme = theme
        super().__init__(parent, bg=theme["card"], highlightthickness=1, highlightbackground=theme["border"], **kwargs)
        self.on_click = on_click
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.is_selected = False

    def update_theme(self, theme):
        self.theme = theme
        bg = self.theme["card_selected"] if self.is_selected else self.theme["card"]
        border = self.theme["accent"] if self.is_selected else self.theme["border"]
        self.config(bg=bg, highlightbackground=border)
        self._propagate_bg(self, bg)

    def _on_enter(self, e):
        if not self.is_selected:
            self.config(bg=self.theme["card_hover"], highlightbackground=self.theme["accent"])
            self._propagate_bg(self, self.theme["card_hover"])

    def _on_leave(self, e):
        if not self.is_selected:
            self.config(bg=self.theme["card"], highlightbackground=self.theme["border"])
            self._propagate_bg(self, self.theme["card"])

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
        bg = self.theme["card_selected"] if selected else self.theme["card"]
        border = self.theme["accent"] if selected else self.theme["border"]
        self.config(bg=bg, highlightbackground=border, highlightthickness=2 if selected else 1)
        self._propagate_bg(self, bg)


class SteamSmartLauncherApp:
    def __init__(self, root, start_minimized=False):
        self.root = root
        self.core = SteamCore()
        self.i18n = I18n(self.core.settings.get("language", "it"))
        self.theme_key = self.core.settings.get("theme", "steam")
        self.theme = get_theme(self.theme_key)
        self.updater = Updater(self.core)

        self.root.title(f"{self.i18n('app_title')} v{APP_VERSION}")
        self.root.geometry("1180x820")
        self.root.minsize(1020, 720)
        self.root.configure(bg=self.theme["bg"])

        self.tray = TrayManager(self.core, self)
        self.tray.start()

        self.core.apply_boot_default_account()

        self.selected_account = None
        self.selected_game = None
        self.view_mode = self.core.settings.get("view_mode", "grid")
        self.filter_mode = "all"
        self.sort_mode = self.core.settings.get("sort_mode", "favorites")

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
            self._trim_memory()

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
                        background=self.theme["header"],
                        troughcolor=self.theme["bg"],
                        bordercolor=self.theme["border"],
                        arrowcolor=self.theme["text"])
        style.configure("TCombobox",
                        fieldbackground=self.theme["entry_bg"],
                        background=self.theme["card_hover"],
                        foreground="#ffffff",
                        darkcolor=self.theme["border"],
                        lightcolor=self.theme["border"])

    def _build_ui(self):
        # 1. Header Bar
        self.header_frame = tk.Frame(self.root, bg=self.theme["header"], height=75, padx=20, pady=12)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        self.title_box = tk.Frame(self.header_frame, bg=self.theme["header"])
        self.title_box.pack(side=tk.LEFT, fill=tk.Y)

        self.title_line = tk.Frame(self.title_box, bg=self.theme["header"])
        self.title_line.pack(anchor="w")

        self.lbl_title = tk.Label(self.title_line, text=self.i18n("header_title"), font=("Segoe UI", 16, "bold"), fg=self.theme["accent"], bg=self.theme["header"])
        self.lbl_title.pack(side=tk.LEFT)

        self.lbl_ver = tk.Label(self.title_line, text=f"v{APP_VERSION}", font=("Segoe UI", 8, "bold"), fg=self.theme["text_muted"], bg=self.theme["card"], padx=5, pady=1)
        self.lbl_ver.pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_subtitle = tk.Label(self.title_box, text=self.i18n("header_subtitle"),
                                font=("Segoe UI", 9), fg=self.theme["text_muted"], bg=self.theme["header"])
        self.lbl_subtitle.pack(anchor="w")

        self.header_right = tk.Frame(self.header_frame, bg=self.theme["header"])
        self.header_right.pack(side=tk.RIGHT, fill=tk.Y)

        self.avatar_label_header = tk.Label(self.header_right, bg=self.theme["header"])
        self.avatar_label_header.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_active_user = tk.Label(self.header_right, text=f"{self.i18n('active_account_prefix')}...",
                                        font=("Segoe UI", 9, "bold"), fg="#ffffff", bg=self.theme["owned_bg"],
                                        padx=12, pady=6, relief=tk.FLAT)
        self.lbl_active_user.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_settings = tk.Button(self.header_right, text=self.i18n("btn_settings"), font=("Segoe UI", 9, "bold"),
                                      fg="#ffffff", bg=self.theme["card"], activebackground=self.theme["card_hover"],
                                      activeforeground="#ffffff", relief=tk.FLAT, padx=10, pady=5,
                                      cursor="hand2", command=self.open_settings_dialog)
        self.btn_settings.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_refresh = tk.Button(self.header_right, text=self.i18n("btn_refresh"), font=("Segoe UI", 9, "bold"),
                                     fg="#ffffff", bg=self.theme["card_hover"], activebackground=self.theme["accent"],
                                     activeforeground="#ffffff", relief=tk.FLAT, padx=10, pady=5,
                                     cursor="hand2", command=self.refresh_data)
        self.btn_refresh.pack(side=tk.LEFT)

        # 2. Main Content
        self.content_frame = tk.Frame(self.root, bg=self.theme["bg"], padx=16, pady=10)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Left Column: Accounts
        self.left_col = tk.Frame(self.content_frame, bg=self.theme["bg"], width=420)
        self.left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        self.acc_header = tk.Frame(self.left_col, bg=self.theme["bg"])
        self.acc_header.pack(fill=tk.X, pady=(0, 6))

        self.lbl_acc_title = tk.Label(self.acc_header, text=self.i18n("accounts_section_title"), font=("Segoe UI", 12, "bold"), fg="#ffffff", bg=self.theme["bg"])
        self.lbl_acc_title.pack(side=tk.LEFT)

        self.accounts_container = self._create_scrollable_container(self.left_col)

        # Right Column: Games
        self.right_col = tk.Frame(self.content_frame, bg=self.theme["bg"])
        self.right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self.games_top_bar = tk.Frame(self.right_col, bg=self.theme["bg"])
        self.games_top_bar.pack(fill=tk.X, pady=(0, 6))

        self.lbl_games_title = tk.Label(self.games_top_bar, text=self.i18n("games_section_title"), font=("Segoe UI", 12, "bold"), fg="#ffffff", bg=self.theme["bg"])
        self.lbl_games_title.pack(side=tk.LEFT)

        self.btn_grid_view = tk.Button(self.games_top_bar, text=self.i18n("btn_grid_view"), font=("Segoe UI", 8, "bold"),
                                       fg="#ffffff", bg=self.theme["card_selected"] if self.view_mode == "grid" else self.theme["card"],
                                       relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=lambda: self._set_view_mode("grid"))
        self.btn_grid_view.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_list_view = tk.Button(self.games_top_bar, text=self.i18n("btn_list_view"), font=("Segoe UI", 8, "bold"),
                                       fg="#ffffff", bg=self.theme["card_selected"] if self.view_mode == "list" else self.theme["card"],
                                       relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=lambda: self._set_view_mode("list"))
        self.btn_list_view.pack(side=tk.RIGHT)

        # Filter Chips & Sorting Row
        self.controls_row = tk.Frame(self.right_col, bg=self.theme["bg"])
        self.controls_row.pack(fill=tk.X, pady=(0, 6))

        self.filter_chips_frame = tk.Frame(self.controls_row, bg=self.theme["bg"])
        self.filter_chips_frame.pack(side=tk.LEFT, fill=tk.X)

        self.sort_frame = tk.Frame(self.controls_row, bg=self.theme["bg"])
        self.sort_frame.pack(side=tk.RIGHT)

        self.lbl_sort = tk.Label(self.sort_frame, text=self.i18n("sort_label"), font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["bg"])
        self.lbl_sort.pack(side=tk.LEFT, padx=(0, 4))

        self.sort_keys = ["favorites", "name", "recent", "size"]
        self.sort_names = [self.i18n(f"sort_{k}") for k in ["favorites", "name_asc", "recent", "size"]]
        cur_sort_idx = self.sort_keys.index(self.sort_mode) if self.sort_mode in self.sort_keys else 0

        self.combo_sort = ttk.Combobox(self.sort_frame, values=self.sort_names, state="readonly", width=18, font=("Segoe UI", 8))
        self.combo_sort.current(cur_sort_idx)
        self.combo_sort.bind("<<ComboboxSelected>>", self._on_sort_changed)
        self.combo_sort.pack(side=tk.RIGHT)

        # Search Bar
        self.search_frame = tk.Frame(self.right_col, bg=self.theme["entry_bg"], highlightthickness=1, highlightbackground=self.theme["border"], pady=2, padx=6)
        self.search_frame.pack(fill=tk.X, pady=(0, 6))

        self.lbl_search_icon = tk.Label(self.search_frame, text="🔍", font=("Segoe UI", 10), fg=self.theme["text_muted"], bg=self.theme["entry_bg"])
        self.lbl_search_icon.pack(side=tk.LEFT, padx=(2, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_input)
        self.entry_search = tk.Entry(self.search_frame, textvariable=self.search_var, font=("Segoe UI", 10),
                                     fg=self.theme["text"], bg=self.theme["entry_bg"], insertbackground=self.theme["accent"], relief=tk.FLAT)
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        self.games_scroll_container = tk.Frame(self.right_col, bg=self.theme["bg"])
        self.games_scroll_container.pack(fill=tk.BOTH, expand=True)
        self.games_container = self._create_scrollable_container(self.games_scroll_container)

        # Selected Game Hero Details Panel
        self.game_details_box = tk.Frame(self.right_col, bg=self.theme["card"], highlightthickness=1, highlightbackground=self.theme["border"], padx=12, pady=10)
        self.game_details_box.pack(fill=tk.X, pady=(8, 0))

        self.det_top = tk.Frame(self.game_details_box, bg=self.theme["card"])
        self.det_top.pack(fill=tk.X)

        self.btn_fav_hero = tk.Button(self.det_top, text="☆", font=("Segoe UI", 12, "bold"), fg="#ffcc00", bg=self.theme["card"],
                                      relief=tk.FLAT, bd=0, padx=2, pady=0, cursor="hand2", command=self._toggle_selected_game_fav)
        self.btn_fav_hero.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_selected_game_name = tk.Label(self.det_top, text=self.i18n("no_game_selected"), font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=self.theme["card"])
        self.lbl_selected_game_name.pack(side=tk.LEFT)

        self.lbl_ownership_badge = tk.Label(self.det_top, text="", font=("Segoe UI", 8, "bold"), fg="#ffffff", bg=self.theme["owned_bg"], padx=6, pady=1)
        self.lbl_ownership_badge.pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_selected_game_size = tk.Label(self.det_top, text="", font=("Segoe UI", 9), fg=self.theme["accent"], bg=self.theme["card"])
        self.lbl_selected_game_size.pack(side=tk.RIGHT)

        # Game Stats & Quick Links
        self.det_links = tk.Frame(self.game_details_box, bg=self.theme["card"])
        self.det_links.pack(fill=tk.X, pady=(4, 6))

        self.lbl_last_played = tk.Label(self.det_links, text="", font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["card"])
        self.lbl_last_played.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_open_folder = tk.Button(self.det_links, text=self.i18n("btn_open_folder"), font=("Segoe UI", 8),
                                         fg=self.theme["text"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"],
                                         relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=self._on_open_game_folder)
        self.btn_open_folder.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_open_store = tk.Button(self.det_links, text=self.i18n("btn_open_store"), font=("Segoe UI", 8),
                                        fg=self.theme["text"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"],
                                        relief=tk.FLAT, padx=8, pady=2, cursor="hand2", command=self._on_open_store_page)
        self.btn_open_store.pack(side=tk.LEFT)

        self.launch_opts_row = tk.Frame(self.game_details_box, bg=self.theme["card"])
        self.launch_opts_row.pack(fill=tk.X, pady=(4, 0))

        self.lbl_lopt = tk.Label(self.launch_opts_row, text=self.i18n("launch_options_label"), font=("Segoe UI", 8, "bold"), fg=self.theme["text_muted"], bg=self.theme["card"])
        self.lbl_lopt.pack(side=tk.LEFT)

        self.launch_opts_var = tk.StringVar()
        self.launch_opts_var.trace_add("write", self._on_launch_opts_changed)
        self.entry_launch_opts = tk.Entry(self.launch_opts_row, textvariable=self.launch_opts_var, font=("Segoe UI", 9),
                                          fg=self.theme["text"], bg=self.theme["entry_bg"], insertbackground=self.theme["accent"],
                                          relief=tk.FLAT, highlightthickness=1, highlightbackground=self.theme["border"])
        self.entry_launch_opts.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), ipady=2)

        # 3. Bottom Action Bar
        self.bottom_bar = tk.Frame(self.root, bg=self.theme["header"], padx=20, pady=12, highlightthickness=1, highlightbackground=self.theme["border"])
        self.bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_preview = tk.Label(self.bottom_bar, text=self.i18n("preview_empty"),
                                    font=("Segoe UI", 10, "bold"), fg=self.theme["accent"], bg=self.theme["header"])
        self.lbl_preview.pack(anchor="w", pady=(0, 8))

        self.actions_row = tk.Frame(self.bottom_bar, bg=self.theme["header"])
        self.actions_row.pack(fill=tk.X)

        self.btn_create_shortcut = tk.Button(self.actions_row, text=self.i18n("btn_create_shortcut"),
                                             font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=self.theme["accent"],
                                             activebackground=self.theme["accent_hover"], activeforeground="#ffffff",
                                             relief=tk.FLAT, padx=16, pady=8, cursor="hand2",
                                             command=self.create_shortcut_action)
        self.btn_create_shortcut.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_launch_now = tk.Button(self.actions_row, text=self.i18n("btn_launch_now"),
                                        font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=self.theme["green"],
                                        activebackground=self.theme["green_hover"], activeforeground="#ffffff",
                                        relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                                        command=self.launch_game_now_action)
        self.btn_launch_now.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_create_all_folder = tk.Button(self.actions_row, text=self.i18n("btn_create_all"),
                                               font=("Segoe UI", 9, "bold"), fg=self.theme["text"], bg=self.theme["card"],
                                               activebackground=self.theme["card_hover"], activeforeground="#ffffff",
                                               relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
                                               command=self.create_all_shortcuts_action)
        self.btn_create_all_folder.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_manage = tk.Button(self.actions_row, text=self.i18n("btn_manage_shortcuts"),
                                    font=("Segoe UI", 9), fg=self.theme["text"], bg=self.theme["card"],
                                    activebackground=self.theme["card_hover"], activeforeground="#ffffff",
                                    relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
                                    command=self.open_manage_shortcuts_dialog)
        self.btn_manage.pack(side=tk.RIGHT)

        self.lbl_status = tk.Label(self.root, text=self.i18n("status_ready", version=APP_VERSION), font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["bg"], anchor="w", padx=20, pady=2)
        self.lbl_status.pack(fill=tk.X, side=tk.BOTTOM)

    def _create_scrollable_container(self, parent):
        container = tk.Frame(parent, bg=self.theme["bg"])
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=self.theme["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.theme["bg"])

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

        self.btn_grid_view.config(bg=self.theme["card_selected"] if mode == "grid" else self.theme["card"])
        self.btn_list_view.config(bg=self.theme["card_selected"] if mode == "list" else self.theme["card"])
        self._render_games()

    def _set_filter_mode(self, mode):
        self.filter_mode = mode
        self._render_filter_chips()
        self._apply_search_filter()

    def _on_sort_changed(self, event=None):
        idx = self.combo_sort.current()
        if idx >= 0 and idx < len(self.sort_keys):
            self.sort_mode = self.sort_keys[idx]
            self.core.settings["sort_mode"] = self.sort_mode
            self.core.save_settings()
            self._apply_search_filter()

    def _render_filter_chips(self):
        for w in self.filter_chips_frame.winfo_children():
            w.destroy()

        chips = [
            (self.i18n("filter_all"), "all"),
            (self.i18n("filter_favorites"), "favorites"),
            (self.i18n("filter_owned"), "owned"),
            (self.i18n("filter_shared"), "shared")
        ]

        for label, mode in chips:
            is_active = (self.filter_mode == mode)
            btn = tk.Button(self.filter_chips_frame, text=label, font=("Segoe UI", 8, "bold" if is_active else "normal"),
                            fg="#ffffff" if is_active else self.theme["text_muted"],
                            bg=self.theme["card_selected"] if is_active else self.theme["card"],
                            activebackground=self.theme["card_hover"], relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
                            command=lambda m=mode: self._set_filter_mode(m))
            btn.pack(side=tk.LEFT, padx=(0, 4))

    def show_toast(self, text, icon="✅"):
        ToastNotification(self.root, text, self.theme, icon=icon)

    def refresh_data(self):
        self.set_status(self.i18n("status_scanning"))
        active_user = self.core.get_current_auto_login_user()

        self.accounts = self.core.get_remembered_accounts()
        self.games = self.core.get_installed_games()
        self.filtered_games = list(self.games)

        active_acc_obj = next((a for a in self.accounts if a["account_name"].lower() == active_user.lower()), None)
        if active_acc_obj:
            self.lbl_active_user.config(text=f"{self.i18n('active_account_prefix')}{active_acc_obj['persona_name']} ({active_acc_obj['account_name']})", bg=self.theme["owned_bg"])
            self._load_header_avatar(active_acc_obj["steamid"], active_acc_obj["persona_name"])
        elif active_user:
            self.lbl_active_user.config(text=f"{self.i18n('active_account_prefix')}{active_user}", bg=self.theme["owned_bg"])
        else:
            self.lbl_active_user.config(text=self.i18n("no_active_account"), bg=self.theme["card"])

        if not self.selected_account and self.accounts:
            self.selected_account = active_acc_obj if active_acc_obj else self.accounts[0]

        if not self.selected_game and self.games:
            self.selected_game = self.games[0]

        self._render_accounts()
        self._render_filter_chips()
        self._apply_search_filter()
        self._update_preview()
        self.tray.update_menu()

        threading.Thread(target=self._async_fetch_assets, daemon=True).start()
        self.set_status(self.i18n("status_detected", acc_count=len(self.accounts), game_count=len(self.games)))

    def _async_check_updates_silent(self):
        res = self.updater.check_for_updates()
        if res.get("success") and res.get("has_update"):
            self.root.after(0, lambda: self._show_update_notification_dialog(res))

    def _show_update_notification_dialog(self, info):
        latest = info.get("latest_version")
        dlg = tk.Toplevel(self.root)
        dlg.title(self.i18n("update_available_title"))
        dlg.geometry("520x380")
        dlg.configure(bg=self.theme["bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_t = tk.Label(dlg, text=self.i18n("update_available_header", version=latest), font=("Segoe UI", 13, "bold"), fg=self.theme["accent"], bg=self.theme["bg"])
        lbl_t.pack(anchor="w", padx=20, pady=(16, 8))

        lbl_sub = tk.Label(dlg, text=self.i18n("update_version_diff", current=APP_VERSION, latest=latest), font=("Segoe UI", 9), fg=self.theme["text_muted"], bg=self.theme["bg"])
        lbl_sub.pack(anchor="w", padx=20, pady=(0, 10))

        box = tk.Frame(dlg, bg=self.theme["card"], highlightthickness=1, highlightbackground=self.theme["border"], padx=12, pady=10)
        box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 12))

        lbl_cl_t = tk.Label(box, text=self.i18n("update_changelog_title"), font=("Segoe UI", 9, "bold"), fg="#ffffff", bg=self.theme["card"])
        lbl_cl_t.pack(anchor="w")

        txt_cl = tk.Text(box, height=8, font=("Segoe UI", 9), fg=self.theme["text"], bg=self.theme["entry_bg"], relief=tk.FLAT, highlightthickness=1, highlightbackground=self.theme["border"])
        txt_cl.insert(tk.END, info.get("changelog") or "No changelog provided.")
        txt_cl.config(state=tk.DISABLED)
        txt_cl.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(dlg, variable=progress_var, maximum=100)

        lbl_dl_status = tk.Label(dlg, text="", font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["bg"])

        btn_row = tk.Frame(dlg, bg=self.theme["bg"])
        btn_row.pack(fill=tk.X, padx=20, pady=(0, 16))

        def start_download():
            btn_update.config(state=tk.DISABLED, text=self.i18n("btn_checking"))
            progress_bar.pack(fill=tk.X, padx=20, pady=(0, 4))
            lbl_dl_status.pack(padx=20, pady=(0, 8))

            def on_progress(pct, downloaded, total):
                progress_var.set(pct)
                lbl_dl_status.config(text=f"Download: {downloaded/(1024*1024):.1f} MB / {total/(1024*1024):.1f} MB ({pct}%)")

            def run():
                try:
                    self.updater.download_and_apply_update(info.get("download_url"), on_progress=on_progress)
                except Exception as ex:
                    dlg.after(0, lambda: messagebox.showerror("Update Error", f"Failed to apply update:\n{ex}"))
                    dlg.after(0, lambda: btn_update.config(state=tk.NORMAL, text=self.i18n("btn_update_now")))

            threading.Thread(target=run, daemon=True).start()

        btn_update = tk.Button(btn_row, text=self.i18n("btn_update_now"), font=("Segoe UI", 10, "bold"),
                               fg="#ffffff", bg=self.theme["green"], activebackground=self.theme["green_hover"],
                               relief=tk.FLAT, padx=14, pady=6, cursor="hand2", command=start_download)
        btn_update.pack(side=tk.LEFT, padx=(0, 8))

        btn_gh = tk.Button(btn_row, text=self.i18n("btn_github_page"), font=("Segoe UI", 9),
                           fg=self.theme["text"], bg=self.theme["card"], activebackground=self.theme["card_hover"],
                           relief=tk.FLAT, padx=12, pady=6, cursor="hand2",
                           command=lambda: os.startfile(info.get("release_url") or "https://github.com"))
        btn_gh.pack(side=tk.LEFT)

        btn_skip = tk.Button(btn_row, text=self.i18n("btn_later"), font=("Segoe UI", 9),
                             fg=self.theme["text_muted"], bg=self.theme["entry_bg"], relief=tk.FLAT,
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
            lbl_empty = tk.Label(self.accounts_container, text=self.i18n("no_accounts_found"),
                                 font=("Segoe UI", 9), fg=self.theme["text_muted"], bg=self.theme["bg"], pady=20)
            lbl_empty.pack(anchor="w")
            return

        for acc in self.accounts:
            acc_name = acc["account_name"]
            persona = acc["persona_name"]
            steamid = acc["steamid"]
            is_active = acc["is_active"]
            tag = self.core.get_account_tag(acc_name)

            card = ModernCard(self.accounts_container, self.theme, on_click=lambda a=acc: self._select_account(a), padx=10, pady=10)
            card.pack(fill=tk.X, pady=4)
            self.account_cards[acc_name] = card

            main_row = tk.Frame(card, bg=self.theme["card"])
            main_row.pack(fill=tk.X)

            avatar_lbl = tk.Label(main_row, bg=self.theme["card"])
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
                avatar_lbl.config(text="👤", font=("Segoe UI", 20), fg=self.theme["accent"])

            info_col = tk.Frame(main_row, bg=self.theme["card"])
            info_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

            top_line = tk.Frame(info_col, bg=self.theme["card"])
            top_line.pack(fill=tk.X)

            lbl_pname = tk.Label(top_line, text=persona, font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=self.theme["card"])
            lbl_pname.pack(side=tk.LEFT)

            if is_active:
                lbl_badge = tk.Label(top_line, text=self.i18n("badge_active"), font=("Segoe UI", 7, "bold"), fg="#ffffff", bg=self.theme["green"], padx=5, pady=1)
                lbl_badge.ignore_hover = True
                lbl_badge.pack(side=tk.RIGHT)

            sub_line = tk.Frame(info_col, bg=self.theme["card"])
            sub_line.pack(fill=tk.X, pady=(2, 2))

            lbl_uname = tk.Label(sub_line, text=f"@{acc_name}", font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["card"])
            lbl_uname.pack(side=tk.LEFT)

            if tag:
                lbl_tag = tk.Label(sub_line, text=f"🏷️ {tag}", font=("Segoe UI", 8, "bold"), fg=self.theme["accent"], bg=self.theme["tag_bg"], padx=4, pady=1)
                lbl_tag.ignore_hover = True
                lbl_tag.pack(side=tk.LEFT, padx=(8, 0))

            btn_row = tk.Frame(card, bg=self.theme["card"])
            btn_row.pack(fill=tk.X, pady=(6, 0))

            btn_switch = tk.Button(btn_row, text=self.i18n("btn_switch"), font=("Segoe UI", 8, "bold"),
                                   fg=self.theme["accent"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"],
                                   relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                   command=lambda a=acc_name: self._switch_only_account(a))
            btn_switch.ignore_hover = True
            btn_switch.pack(side=tk.LEFT, padx=(0, 4))

            btn_tag = tk.Button(btn_row, text=self.i18n("btn_tag"), font=("Segoe UI", 8),
                                fg=self.theme["text"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"],
                                relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                                command=lambda a=acc_name: self._edit_account_tag(a))
            btn_tag.ignore_hover = True
            btn_tag.pack(side=tk.LEFT, padx=(0, 4))

            btn_profile = tk.Button(btn_row, text=self.i18n("btn_profile"), font=("Segoe UI", 8),
                                    fg=self.theme["text"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"],
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
            lbl_empty = tk.Label(self.games_container, text=self.i18n("no_games_found"), font=("Segoe UI", 9), fg=self.theme["text_muted"], bg=self.theme["bg"], pady=20)
            lbl_empty.pack()
            return

        if self.view_mode == "grid":
            self._render_games_grid()
        else:
            self._render_games_list()

    def _render_games_grid(self):
        grid_frame = tk.Frame(self.games_container, bg=self.theme["bg"])
        grid_frame.pack(fill=tk.BOTH, expand=True)

        cols = self.grid_cols
        for i, game in enumerate(self.filtered_games):
            appid = game["appid"]
            name = game["name"]
            poster_path = self.core.get_cached_poster_path(appid)
            owner_info = self.core.get_game_ownership(game, self.selected_account, self.accounts, i18n=self.i18n)
            is_fav = self.core.is_favorite(appid)

            r = i // cols
            c = i % cols

            card = ModernCard(grid_frame, self.theme, on_click=lambda g=game: self._select_game(g), padx=4, pady=4)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            self.game_cards[appid] = card

            poster_lbl = tk.Label(card, bg=self.theme["card"])
            poster_lbl.pack(fill=tk.BOTH, expand=True)

            if poster_path and os.path.exists(poster_path):
                try:
                    img = Image.open(poster_path).resize((110, 160), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.poster_images[appid] = photo
                    poster_lbl.config(image=photo)
                except Exception:
                    poster_lbl.config(text="🎮\n" + name[:12], font=("Segoe UI", 9, "bold"), fg=self.theme["accent"], width=12, height=8)
            else:
                poster_lbl.config(text="🎮\n" + name[:12], font=("Segoe UI", 9, "bold"), fg=self.theme["accent"], width=12, height=8)

            badge_box = tk.Frame(card, bg=self.theme["card"])
            badge_box.pack(fill=tk.X, pady=(2, 0))

            btn_fav = tk.Button(badge_box, text="★" if is_fav else "☆", font=("Segoe UI", 8, "bold"),
                                fg="#ffcc00" if is_fav else self.theme["text_muted"], bg=self.theme["card"],
                                relief=tk.FLAT, bd=0, padx=2, pady=0, cursor="hand2",
                                command=lambda aid=appid, g=game: self._toggle_game_fav(aid, g))
            btn_fav.ignore_hover = True
            btn_fav.pack(side=tk.LEFT, padx=(2, 2))

            badge_color = self.theme["shared_bg"] if owner_info["is_shared"] else self.theme["owned_bg"]
            badge_txt = self.i18n("badge_shared_grid") if owner_info["is_shared"] else self.i18n("badge_owned_grid")
            lbl_own = tk.Label(badge_box, text=badge_txt, font=("Segoe UI", 7, "bold"), fg="#ffffff", bg=badge_color, padx=4, pady=1)
            lbl_own.pack(side=tk.LEFT)

            short_title = name if len(name) <= 15 else name[:14] + "…"
            lbl_t = tk.Label(card, text=short_title, font=("Segoe UI", 8, "bold"), fg="#ffffff", bg=self.theme["card"])
            lbl_t.pack(pady=(1, 0))

            if self.selected_game and self.selected_game["appid"] == appid:
                card.set_selected(True)

    def _render_games_list(self):
        for game in self.filtered_games:
            appid = game["appid"]
            name = game["name"]
            size_str = game["size_str"]
            drive = game["drive"]
            owner_info = self.core.get_game_ownership(game, self.selected_account, self.accounts, i18n=self.i18n)
            is_fav = self.core.is_favorite(appid)

            card = ModernCard(self.games_container, self.theme, on_click=lambda g=game: self._select_game(g), padx=12, pady=8)
            card.pack(fill=tk.X, pady=3)
            self.game_cards[appid] = card

            row = tk.Frame(card, bg=self.theme["card"])
            row.pack(fill=tk.X)

            btn_fav = tk.Button(row, text="★" if is_fav else "☆", font=("Segoe UI", 11, "bold"),
                                fg="#ffcc00" if is_fav else self.theme["text_muted"], bg=self.theme["card"],
                                relief=tk.FLAT, bd=0, padx=2, pady=0, cursor="hand2",
                                command=lambda aid=appid, g=game: self._toggle_game_fav(aid, g))
            btn_fav.ignore_hover = True
            btn_fav.pack(side=tk.LEFT, padx=(0, 6))

            lbl_gname = tk.Label(row, text=f"🎮  {name}", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=self.theme["card"])
            lbl_gname.pack(side=tk.LEFT)

            info_box = tk.Frame(row, bg=self.theme["card"])
            info_box.pack(side=tk.RIGHT)

            badge_color = self.theme["shared_bg"] if owner_info["is_shared"] else self.theme["owned_bg"]
            lbl_own = tk.Label(info_box, text=owner_info["badge_text"], font=("Segoe UI", 8, "bold"), fg="#ffffff", bg=badge_color, padx=6, pady=2)
            lbl_own.pack(side=tk.LEFT, padx=(0, 6))

            lbl_size = tk.Label(info_box, text=self.i18n("disk_space", size=size_str, drive=drive), font=("Segoe UI", 8), fg=self.theme["accent"], bg=self.theme["entry_bg"], padx=6, pady=2)
            lbl_size.pack(side=tk.LEFT, padx=(0, 6))

            lbl_appid = tk.Label(info_box, text=f"ID: {appid}", font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["entry_bg"], padx=6, pady=2)
            lbl_appid.pack(side=tk.LEFT)

            if self.selected_game and self.selected_game["appid"] == appid:
                card.set_selected(True)

    def _toggle_game_fav(self, appid, game):
        new_fav = self.core.toggle_favorite(appid)
        msg_key = "toast_fav_added" if new_fav else "toast_fav_removed"
        self.show_toast(self.i18n(msg_key, game=game["name"]), icon="⭐" if new_fav else "⚪")
        self._apply_search_filter()
        self._update_preview()

    def _toggle_selected_game_fav(self):
        if self.selected_game:
            self._toggle_game_fav(self.selected_game["appid"], self.selected_game)

    def _on_search_input(self, *args):
        if self._search_timer:
            self.root.after_cancel(self._search_timer)
        self._search_timer = self.root.after(180, self._apply_search_filter)

    def _apply_search_filter(self):
        query = self.search_var.get().strip().lower()
        res = list(self.games)

        # 1. Filter
        if self.filter_mode == "favorites":
            res = [g for g in res if self.core.is_favorite(g["appid"])]
        elif self.filter_mode == "owned":
            res = [g for g in res if self.core.get_game_ownership(g, self.selected_account, self.accounts, i18n=self.i18n)["is_owner"]]
        elif self.filter_mode == "shared":
            res = [g for g in res if self.core.get_game_ownership(g, self.selected_account, self.accounts, i18n=self.i18n)["is_shared"]]

        if query:
            res = [g for g in res if query in g["name"].lower() or query in g["appid"]]

        # 2. Sort
        if self.sort_mode == "favorites":
            res.sort(key=lambda g: (not self.core.is_favorite(g["appid"]), g["name"].lower()))
        elif self.sort_mode == "name":
            res.sort(key=lambda g: g["name"].lower())
        elif self.sort_mode == "recent":
            res.sort(key=lambda g: g.get("last_played_ts", 0), reverse=True)
        elif self.sort_mode == "size":
            res.sort(key=lambda g: g.get("size_bytes", 0), reverse=True)

        self.filtered_games = res
        self._render_games()

    def _select_account(self, acc):
        self.selected_account = acc
        for acc_name, card in self.account_cards.items():
            card.set_selected(acc_name == acc["account_name"])
        self._apply_search_filter()
        self._update_preview()

    def _select_game(self, game):
        self.selected_game = game
        for appid, card in self.game_cards.items():
            card.set_selected(appid == game["appid"])
        self._update_preview()

    def _update_preview(self):
        if self.selected_game:
            g = self.selected_game
            owner_info = self.core.get_game_ownership(g, self.selected_account, self.accounts, i18n=self.i18n)
            is_fav = self.core.is_favorite(g["appid"])

            self.btn_fav_hero.config(text="★" if is_fav else "☆", fg="#ffcc00" if is_fav else self.theme["text_muted"])
            self.lbl_selected_game_name.config(text=f"🎮 {g['name']} (ID: {g['appid']})")
            self.lbl_ownership_badge.config(
                text=owner_info["badge_text"],
                bg=self.theme["shared_bg"] if owner_info["is_shared"] else self.theme["owned_bg"]
            )
            self.lbl_selected_game_size.config(text=self.i18n("space_on_drive", size=g.get('size_str', 'N/D'), drive=g.get('drive', 'C:')))
            
            lp_str = g.get('last_played_str') if g.get('last_played_ts', 0) > 0 else self.i18n("never_played")
            self.lbl_last_played.config(text=self.i18n("last_session", date=lp_str))

            acc_name = self.selected_account["account_name"] if self.selected_account else ""
            opts = self.core.get_game_launch_options(g["appid"], acc_name)
            self.launch_opts_var.set(opts)
        else:
            self.btn_fav_hero.config(text="☆", fg=self.theme["text_muted"])
            self.lbl_selected_game_name.config(text=self.i18n("no_game_selected"))
            self.lbl_ownership_badge.config(text="")
            self.lbl_selected_game_size.config(text="")
            self.lbl_last_played.config(text="")

        if self.selected_game and self.selected_account:
            g_name = self.selected_game["name"]
            p_name = self.selected_account["persona_name"]
            u_name = self.selected_account["account_name"]
            l_opts = self.launch_opts_var.get().strip()
            opts_str = f" | Options: '{l_opts}'" if l_opts else ""
            self.lbl_preview.config(text=self.i18n("preview_ready", game=g_name, persona=p_name, user=u_name, opts=opts_str))
            self.btn_create_shortcut.config(state=tk.NORMAL)
            self.btn_launch_now.config(state=tk.NORMAL)
            self.btn_create_all_folder.config(state=tk.NORMAL)
        else:
            self.lbl_preview.config(text=self.i18n("preview_empty"))
            self.btn_create_shortcut.config(state=tk.DISABLED)
            self.btn_launch_now.config(state=tk.DISABLED)

    def _on_launch_opts_changed(self, *args):
        if self.selected_game:
            opts = self.launch_opts_var.get().strip()
            acc_name = self.selected_account["account_name"] if self.selected_account else ""
            self.core.set_game_launch_options(self.selected_game["appid"], opts, acc_name)

    def _edit_account_tag(self, account_name):
        current_tag = self.core.get_account_tag(account_name)
        new_tag = simpledialog.askstring("Tag / Note", f"Tag for @{account_name}\n(e.g. Main, Smurf, Co-op):", initialvalue=current_tag, parent=self.root)
        if new_tag is not None:
            self.core.set_account_tag(account_name, new_tag)
            self.refresh_data()

    def _switch_only_account(self, account_name):
        is_playing, appid = self.core.is_game_running()
        if is_playing:
            messagebox.showerror(self.i18n("game_running_title"), self.i18n("game_running_msg", appid=appid))
            return

        res = messagebox.askyesno(self.i18n("confirm_switch_title"), self.i18n("confirm_switch_msg", account=account_name))
        if not res:
            return

        self.set_status(f"Switching to {account_name}...")
        def run():
            try:
                self.core.switch_account_and_launch(account_name, appid=None)
                self.root.after(2000, self.refresh_data)
                self.root.after(0, lambda: self.show_toast(self.i18n("toast_switch_done", account=account_name)))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Switch Error", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_open_game_folder(self):
        if self.selected_game and self.selected_game.get("full_dir"):
            self.core.open_game_directory(self.selected_game["full_dir"])
        else:
            messagebox.showinfo("Info", "Directory not available.")

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

        try:
            shortcut_path = self.core.create_desktop_shortcut(appid, game_name, account_name, persona_name, launch_args=launch_args)
            filename = os.path.basename(shortcut_path)
            self.show_toast(self.i18n("toast_shortcut_created", filename=filename), icon="⭐")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create shortcut:\n{e}")

    def create_all_shortcuts_action(self):
        if not self.selected_account:
            return

        account_name = self.selected_account["account_name"]
        persona_name = self.selected_account["persona_name"]

        res = messagebox.askyesno(self.i18n("confirm_generate_all_title"), self.i18n("confirm_generate_all_msg", count=len(self.games), persona=persona_name))
        if not res:
            return

        try:
            target_dir, created = self.core.create_all_shortcuts_for_account(account_name, persona_name, in_subfolder=True)
            self.show_toast(self.i18n("toast_folder_created", count=len(created)), icon="📁")
            os.startfile(target_dir)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create folder:\n{e}")

    def launch_game_now_action(self):
        if not self.selected_game or not self.selected_account:
            return

        is_playing, active_appid = self.core.is_game_running()
        if is_playing and active_appid != int(self.selected_game["appid"]):
            messagebox.showerror(self.i18n("game_running_title"), f"Another Steam game (ID: {active_appid}) is running.")
            return

        appid = self.selected_game["appid"]
        game_name = self.selected_game["name"]
        account_name = self.selected_account["account_name"]
        persona_name = self.selected_account["persona_name"]
        launch_args = self.launch_opts_var.get().strip()

        def run():
            try:
                self.core.switch_account_and_launch(account_name, appid, launch_args=launch_args)
                self.root.after(3000, self.refresh_data)
                self.root.after(0, lambda: self.show_toast(self.i18n("toast_launching", game=game_name, persona=persona_name), icon="🚀"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Launch Error", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def open_manage_shortcuts_dialog(self):
        shortcuts = self.core.get_existing_smart_shortcuts()

        dlg = tk.Toplevel(self.root)
        dlg.title(self.i18n("shortcuts_dlg_title"))
        dlg.geometry("640x480")
        dlg.configure(bg=self.theme["bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_dlg_title = tk.Label(dlg, text=self.i18n("shortcuts_dlg_header"), font=("Segoe UI", 12, "bold"), fg=self.theme["accent"], bg=self.theme["bg"])
        lbl_dlg_title.pack(anchor="w", padx=16, pady=(16, 8))

        box = tk.Frame(dlg, bg=self.theme["card"], highlightthickness=1, highlightbackground=self.theme["border"])
        box.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        container = self._create_scrollable_container(box)

        if not shortcuts:
            lbl_none = tk.Label(container, text=self.i18n("shortcuts_dlg_empty"), font=("Segoe UI", 9), fg=self.theme["text_muted"], bg=self.theme["bg"], pady=20)
            lbl_none.pack()
        else:
            for sc in shortcuts:
                item = tk.Frame(container, bg=self.theme["card"], highlightthickness=1, highlightbackground=self.theme["border"], padx=10, pady=8)
                item.pack(fill=tk.X, pady=3, padx=4)

                row1 = tk.Frame(item, bg=self.theme["card"])
                row1.pack(fill=tk.X)

                lbl_fn = tk.Label(row1, text=f"[{sc['folder']}]  {sc['filename']}", font=("Segoe UI", 9, "bold"), fg="#ffffff", bg=self.theme["card"])
                lbl_fn.pack(side=tk.LEFT)

                def delete_sc(path=sc["path"], row_widget=item):
                    if messagebox.askyesno("Delete", f"Delete shortcut:\n{os.path.basename(path)}?"):
                        try:
                            os.remove(path)
                            row_widget.destroy()
                            self.show_toast(self.i18n("toast_shortcut_deleted"), icon="🗑️")
                        except Exception as ex:
                            messagebox.showerror("Error", f"Failed: {ex}")

                btn_del = tk.Button(row1, text=self.i18n("btn_delete"), font=("Segoe UI", 8), fg="#ff5555", bg=self.theme["entry_bg"],
                                    relief=tk.FLAT, padx=6, pady=2, cursor="hand2", command=delete_sc)
                btn_del.pack(side=tk.RIGHT)

                lbl_sub = tk.Label(item, text=f"AppID: {sc['appid']}  |  Account: {sc['account']}  |  Args: '{sc['launch_args'] or 'None'}'",
                                   font=("Segoe UI", 8), fg=self.theme["text_muted"], bg=self.theme["card"])
                lbl_sub.pack(anchor="w", pady=(2, 0))

        btn_close = tk.Button(dlg, text=self.i18n("btn_close"), font=("Segoe UI", 9), fg=self.theme["text"], bg=self.theme["card_hover"],
                              relief=tk.FLAT, padx=16, pady=6, cursor="hand2", command=dlg.destroy)
        btn_close.pack(pady=(0, 14))

    def open_settings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(self.i18n("settings_title"))
        dlg.geometry("580x620")
        dlg.configure(bg=self.theme["bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_title = tk.Label(dlg, text=self.i18n("settings_header"), font=("Segoe UI", 13, "bold"), fg=self.theme["accent"], bg=self.theme["bg"])
        lbl_title.pack(anchor="w", padx=20, pady=(16, 12))

        box = tk.Frame(dlg, bg=self.theme["card"], highlightthickness=1, highlightbackground=self.theme["border"], padx=16, pady=16)
        box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 16))

        is_autostart, _ = self.core.is_windows_autostart_enabled()
        var_autostart = tk.BooleanVar(value=is_autostart)
        var_start_minimized = tk.BooleanVar(value=self.core.settings.get("start_minimized", False))
        var_close_to_tray = tk.BooleanVar(value=self.core.settings.get("close_to_tray", True))
        var_notifications = tk.BooleanVar(value=self.core.settings.get("show_notifications", True))
        var_auto_update = tk.BooleanVar(value=self.core.settings.get("auto_check_updates", True))

        cb_autostart = tk.Checkbutton(box, text=self.i18n("setting_autostart"),
                                      variable=var_autostart, font=("Segoe UI", 9), fg="#ffffff", bg=self.theme["card"],
                                      selectcolor=self.theme["entry_bg"], activebackground=self.theme["card"], activeforeground="#ffffff")
        cb_autostart.pack(anchor="w", pady=3)

        cb_min = tk.Checkbutton(box, text=self.i18n("setting_start_minimized"),
                                variable=var_start_minimized, font=("Segoe UI", 9), fg="#ffffff", bg=self.theme["card"],
                                selectcolor=self.theme["entry_bg"], activebackground=self.theme["card"], activeforeground="#ffffff")
        cb_min.pack(anchor="w", pady=3)

        cb_close = tk.Checkbutton(box, text=self.i18n("setting_close_to_tray"),
                                  variable=var_close_to_tray, font=("Segoe UI", 9), fg="#ffffff", bg=self.theme["card"],
                                  selectcolor=self.theme["entry_bg"], activebackground=self.theme["card"], activeforeground="#ffffff")
        cb_close.pack(anchor="w", pady=3)

        cb_notif = tk.Checkbutton(box, text=self.i18n("setting_notifications"),
                                  variable=var_notifications, font=("Segoe UI", 9), fg="#ffffff", bg=self.theme["card"],
                                  selectcolor=self.theme["entry_bg"], activebackground=self.theme["card"], activeforeground="#ffffff")
        cb_notif.pack(anchor="w", pady=3)

        cb_upd = tk.Checkbutton(box, text=self.i18n("setting_auto_update"),
                                variable=var_auto_update, font=("Segoe UI", 9), fg="#ffffff", bg=self.theme["card"],
                                selectcolor=self.theme["entry_bg"], activebackground=self.theme["card"], activeforeground="#ffffff")
        cb_upd.pack(anchor="w", pady=3)

        tk.Frame(box, bg=self.theme["border"], height=1).pack(fill=tk.X, pady=6)

        # Theme Selection
        lbl_thm = tk.Label(box, text=self.i18n("setting_theme"), font=("Segoe UI", 9, "bold"), fg=self.theme["text"], bg=self.theme["card"])
        lbl_thm.pack(anchor="w")

        theme_keys = ["steam", "oled", "cyberpunk", "midnight", "forest"]
        theme_names = [self.i18n(f"theme_{k}") for k in theme_keys]
        cur_thm_idx = theme_keys.index(self.theme_key) if self.theme_key in theme_keys else 0

        combo_thm = ttk.Combobox(box, values=theme_names, state="readonly", font=("Segoe UI", 9))
        combo_thm.current(cur_thm_idx)
        combo_thm.pack(fill=tk.X, pady=(2, 6))

        # Language Selection
        lbl_lang = tk.Label(box, text=self.i18n("setting_language"), font=("Segoe UI", 9, "bold"), fg=self.theme["text"], bg=self.theme["card"])
        lbl_lang.pack(anchor="w")

        lang_options = ["🇮🇹 Italiano", "🇬🇧 English"]
        lang_codes = ["it", "en"]
        cur_lang = self.core.settings.get("language", "it")
        combo_lang = ttk.Combobox(box, values=lang_options, state="readonly", font=("Segoe UI", 9))
        combo_lang.current(0 if cur_lang == "it" else 1)
        combo_lang.pack(fill=tk.X, pady=(2, 6))

        # Default Account
        lbl_def = tk.Label(box, text=self.i18n("setting_default_account"), font=("Segoe UI", 9, "bold"), fg=self.theme["text"], bg=self.theme["card"])
        lbl_def.pack(anchor="w")

        account_options = [self.i18n("setting_default_none")] + [f"{a['persona_name']} (@{a['account_name']})" for a in self.accounts]
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
        combo_def.pack(fill=tk.X, pady=(2, 6))

        # GitHub Repo
        lbl_repo = tk.Label(box, text=self.i18n("setting_github_repo"), font=("Segoe UI", 9, "bold"), fg=self.theme["text"], bg=self.theme["card"])
        lbl_repo.pack(anchor="w")

        repo_frame = tk.Frame(box, bg=self.theme["card"])
        repo_frame.pack(fill=tk.X, pady=(2, 0))

        var_repo = tk.StringVar(value=self.core.settings.get("github_repo", DEFAULT_GITHUB_REPO))
        entry_repo = tk.Entry(repo_frame, textvariable=var_repo, font=("Segoe UI", 9), fg=self.theme["text"], bg=self.theme["entry_bg"],
                              insertbackground=self.theme["accent"], relief=tk.FLAT, highlightthickness=1, highlightbackground=self.theme["border"])
        entry_repo.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        def manual_check():
            self.core.settings["github_repo"] = var_repo.get().strip()
            self.core.save_settings()
            btn_chk.config(state=tk.DISABLED, text=self.i18n("btn_checking"))
            def run():
                res = self.updater.check_for_updates()
                dlg.after(0, lambda: btn_chk.config(state=tk.NORMAL, text=self.i18n("btn_check_updates")))
                if res.get("success"):
                    if res.get("has_update"):
                        dlg.after(0, lambda: self._show_update_notification_dialog(res))
                    else:
                        dlg.after(0, lambda: messagebox.showinfo("Info", f"You are running the latest version (v{APP_VERSION})."))
                else:
                    dlg.after(0, lambda: messagebox.showwarning("Update Check", res.get("error", "Unknown error.")))
            threading.Thread(target=run, daemon=True).start()

        btn_chk = tk.Button(repo_frame, text=self.i18n("btn_check_updates"), font=("Segoe UI", 8, "bold"),
                            fg="#ffffff", bg=self.theme["card_hover"], activebackground=self.theme["accent"],
                            relief=tk.FLAT, padx=10, pady=3, cursor="hand2", command=manual_check)
        btn_chk.pack(side=tk.RIGHT, padx=(6, 0))

        def save_and_close():
            self.core.settings["start_minimized"] = var_start_minimized.get()
            self.core.settings["close_to_tray"] = var_close_to_tray.get()
            self.core.settings["show_notifications"] = var_notifications.get()
            self.core.settings["auto_check_updates"] = var_auto_update.get()
            self.core.settings["github_repo"] = var_repo.get().strip()

            new_theme_key = theme_keys[combo_thm.current()]
            theme_changed = (new_theme_key != self.theme_key)
            self.theme_key = new_theme_key
            self.theme = get_theme(new_theme_key)
            self.core.settings["theme"] = new_theme_key

            new_lang = lang_codes[combo_lang.current()]
            lang_changed = (new_lang != self.i18n.lang)
            self.core.settings["language"] = new_lang
            self.i18n.set_language(new_lang)

            autostart_val = var_autostart.get()
            self.core.set_windows_autostart(autostart_val, start_minimized=var_start_minimized.get())

            selected_acc_idx = combo_def.current()
            if selected_acc_idx > 0 and selected_acc_idx < len(account_usernames):
                self.core.settings["default_account_on_boot"] = account_usernames[selected_acc_idx]
            else:
                self.core.settings["default_account_on_boot"] = ""

            self.core.save_settings()
            self.show_toast(self.i18n("toast_settings_saved"))
            dlg.destroy()

            if theme_changed or lang_changed:
                self._apply_full_theme_and_lang()

        btn_save = tk.Button(dlg, text=self.i18n("btn_save_settings"), font=("Segoe UI", 10, "bold"),
                             fg="#ffffff", bg=self.theme["green"], activebackground=self.theme["green_hover"],
                             relief=tk.FLAT, padx=16, pady=6, cursor="hand2", command=save_and_close)
        btn_save.pack(pady=(0, 16))

    def _apply_full_theme_and_lang(self):
        self.root.configure(bg=self.theme["bg"])
        self._setup_styles()

        self.root.title(f"{self.i18n('app_title')} v{APP_VERSION}")
        self.header_frame.config(bg=self.theme["header"])
        self.title_box.config(bg=self.theme["header"])
        self.title_line.config(bg=self.theme["header"])
        self.lbl_title.config(text=self.i18n("header_title"), fg=self.theme["accent"], bg=self.theme["header"])
        self.lbl_ver.config(fg=self.theme["text_muted"], bg=self.theme["card"])
        self.lbl_subtitle.config(text=self.i18n("header_subtitle"), fg=self.theme["text_muted"], bg=self.theme["header"])
        self.header_right.config(bg=self.theme["header"])
        self.avatar_label_header.config(bg=self.theme["header"])
        self.lbl_active_user.config(bg=self.theme["owned_bg"])
        self.btn_settings.config(text=self.i18n("btn_settings"), bg=self.theme["card"], activebackground=self.theme["card_hover"])
        self.btn_refresh.config(text=self.i18n("btn_refresh"), bg=self.theme["card_hover"], activebackground=self.theme["accent"])

        self.content_frame.config(bg=self.theme["bg"])
        self.left_col.config(bg=self.theme["bg"])
        self.acc_header.config(bg=self.theme["bg"])
        self.lbl_acc_title.config(text=self.i18n("accounts_section_title"), bg=self.theme["bg"])
        self.right_col.config(bg=self.theme["bg"])
        self.games_top_bar.config(bg=self.theme["bg"])
        self.lbl_games_title.config(text=self.i18n("games_section_title"), bg=self.theme["bg"])
        self.btn_grid_view.config(text=self.i18n("btn_grid_view"), bg=self.theme["card_selected"] if self.view_mode == "grid" else self.theme["card"])
        self.btn_list_view.config(text=self.i18n("btn_list_view"), bg=self.theme["card_selected"] if self.view_mode == "list" else self.theme["card"])
        self.controls_row.config(bg=self.theme["bg"])
        self.filter_chips_frame.config(bg=self.theme["bg"])
        self.sort_frame.config(bg=self.theme["bg"])
        self.lbl_sort.config(text=self.i18n("sort_label"), fg=self.theme["text_muted"], bg=self.theme["bg"])

        self.sort_names = [self.i18n(f"sort_{k}") for k in ["favorites", "name_asc", "recent", "size"]]
        self.combo_sort.config(values=self.sort_names)

        self.search_frame.config(bg=self.theme["entry_bg"], highlightbackground=self.theme["border"])
        self.lbl_search_icon.config(fg=self.theme["text_muted"], bg=self.theme["entry_bg"])
        self.entry_search.config(fg=self.theme["text"], bg=self.theme["entry_bg"], insertbackground=self.theme["accent"])

        self.games_scroll_container.config(bg=self.theme["bg"])
        self.game_details_box.config(bg=self.theme["card"], highlightbackground=self.theme["border"])
        self.det_top.config(bg=self.theme["card"])
        self.lbl_selected_game_name.config(text=self.i18n("no_game_selected"), bg=self.theme["card"])
        self.lbl_selected_game_size.config(fg=self.theme["accent"], bg=self.theme["card"])
        self.det_links.config(bg=self.theme["card"])
        self.lbl_last_played.config(fg=self.theme["text_muted"], bg=self.theme["card"])
        self.btn_open_folder.config(text=self.i18n("btn_open_folder"), fg=self.theme["text"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"])
        self.btn_open_store.config(text=self.i18n("btn_open_store"), fg=self.theme["text"], bg=self.theme["entry_bg"], activebackground=self.theme["card_hover"])
        self.launch_opts_row.config(bg=self.theme["card"])
        self.lbl_lopt.config(text=self.i18n("launch_options_label"), fg=self.theme["text_muted"], bg=self.theme["card"])
        self.entry_launch_opts.config(fg=self.theme["text"], bg=self.theme["entry_bg"], insertbackground=self.theme["accent"], highlightbackground=self.theme["border"])

        self.bottom_bar.config(bg=self.theme["header"], highlightbackground=self.theme["border"])
        self.lbl_preview.config(fg=self.theme["accent"], bg=self.theme["header"])
        self.actions_row.config(bg=self.theme["header"])
        self.btn_create_shortcut.config(text=self.i18n("btn_create_shortcut"), bg=self.theme["accent"], activebackground=self.theme["accent_hover"])
        self.btn_launch_now.config(text=self.i18n("btn_launch_now"), bg=self.theme["green"], activebackground=self.theme["green_hover"])
        self.btn_create_all_folder.config(text=self.i18n("btn_create_all"), fg=self.theme["text"], bg=self.theme["card"], activebackground=self.theme["card_hover"])
        self.btn_manage.config(text=self.i18n("btn_manage_shortcuts"), fg=self.theme["text"], bg=self.theme["card"], activebackground=self.theme["card_hover"])
        self.lbl_status.config(text=self.i18n("status_ready", version=APP_VERSION), fg=self.theme["text_muted"], bg=self.theme["bg"])

        self._render_filter_chips()
        self.refresh_data()

    def _trim_memory(self):
        """Releases image buffers, runs garbage collection, and trims working set in Windows."""
        self.avatar_images.clear()
        self.poster_images.clear()
        self.capsule_images.clear()
        self.icon_images.clear()
        gc.collect()
        try:
            # Native Win32 call: empties working set to pagefile/standby, dropping RAM to <10MB
            ctypes.windll.kernel32.SetProcessWorkingSetSize(
                ctypes.windll.kernel32.GetCurrentProcess(), -1, -1
            )
        except Exception:
            pass

    def on_window_close(self):
        if self.core.settings.get("close_to_tray", True):
            self.root.withdraw()
            self._trim_memory()
            if self.core.settings.get("show_notifications", True) and self.tray and self.tray.icon:
                try:
                    self.tray.icon.notify("Steam Smart Switcher is running in system tray.", "Steam Smart Switcher")
                except Exception:
                    pass
        else:
            self.quit_completely()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_data()

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
            ctypes.windll.user32.MessageBoxW(0, f"Steam Smart Switcher:\n\n{ex}", "Steam Smart Switcher", 0x30 | 0x0)
            sys.exit(1)
        sys.exit(0)

    # Standard Mode: Launch GUI
    root = tk.Tk()
    app = SteamSmartLauncherApp(root, start_minimized=args.minimized)
    root.mainloop()

if __name__ == "__main__":
    main()
