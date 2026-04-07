# ui/app.py — Premium Dark UI
# Design System: Premium Gold (#C6A96B) + Layered Surfaces

import os
import sys
import queue
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from datetime import datetime

from config import THEME, APP_NAME, APP_VERSION
from db.database import Database
from core.search import SearchEngine
from core.worker import IndexWorker
from core.watcher import FileWatcher
from core.parsers import extract_content
from utils.file_utils import format_size
from utils.text_utils import tr_lower
from logger import log

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

T = THEME


class VastarionApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1200x800")
        self.minsize(950, 650)
        self.configure(fg_color=T["bg"])

        self._set_icon()

        # Core
        self.ui_queue = queue.Queue()
        self.db = Database()
        self.search_engine = SearchEngine(self.db)
        self.worker = IndexWorker(self.db, self.ui_queue)
        self.watcher = FileWatcher(self.db)
        self.watcher.on_change(lambda n: self.ui_queue.put(("watcher_update", n)))
        self.watcher.start()

        self._search_after_id = None
        self._content_cache = {}
        self._result_paths = []
        self._hover_item = None
        self._folder_hover_idx = None
        self._logo_refs = {}

        self._build_ui()
        self._process_queue()
        self._update_stats()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Helpers ──────────────────────────────────────────

    def _set_icon(self):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets'))
        ico = os.path.join(base, 'logo.ico')
        png = os.path.join(base, 'logo.png')
        try:
            if os.path.exists(ico):
                self.iconbitmap(ico)
            elif os.path.exists(png):
                icon = tk.PhotoImage(file=png)
                self.iconphoto(True, icon)
                self._logo_refs["icon_tk"] = icon
        except Exception as e:
            log.warning(f"Ikon ayarlanamadi: {e}")

    def _load_logo(self, height):
        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png'))
        if not os.path.exists(logo_path):
            return None
        try:
            from PIL import Image
            key = f"logo_{height}"
            if key not in self._logo_refs:
                pil_img = Image.open(logo_path)
                ratio = pil_img.width / pil_img.height
                width = int(height * ratio)
                self._logo_refs[key] = ctk.CTkImage(
                    light_image=pil_img, dark_image=pil_img,
                    size=(width, height)
                )
            return self._logo_refs[key]
        except Exception as e:
            log.warning(f"Logo yuklenemedi: {e}")
            return None

    # ══════════════════════════════════════════════════════
    # BUILD UI
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)   # main area expands

        self._build_header()       # row 0
        self._build_search_bar()   # row 1
        self._build_main_area()    # row 2
        self._build_status_bar()   # row 3

    # ── HEADER ───────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=T["bg"], corner_radius=0, height=120)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        # Brand: Logo + Text
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w", padx=32, pady=16)

        logo = self._load_logo(100)
        if logo:
            ctk.CTkLabel(brand, text="", image=logo).pack(side="left", padx=(0, 20))

        text_block = ctk.CTkFrame(brand, fg_color="transparent")
        text_block.pack(side="left", anchor="s", pady=(0, 4))

        ctk.CTkLabel(
            text_block, text="Scanner",
            font=ctk.CTkFont(family="Georgia", size=24, slant="italic"),
            text_color=T["gold"]
        ).pack(anchor="w")

        # Ince gold cizgi (nav-logo::after efekti)
        tk.Canvas(
            text_block, width=40, height=1, bg=T["gold"], highlightthickness=0
        ).pack(anchor="w", pady=(3, 5))

        ctk.CTkLabel(
            text_block, text="File Intelligence Engine",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=T["text_muted"]
        ).pack(anchor="w")

        # Sag: Stats
        self.lbl_stats = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=T["text_muted"]
        )
        self.lbl_stats.grid(row=0, column=1, sticky="e", padx=32)

        # Border bottom
        tk.Canvas(
            header, height=1, bg=T["bg"], highlightthickness=0
        ).grid(row=1, column=0, columnspan=2, sticky="ew")

    # ── SEARCH BAR ───────────────────────────────────────

    def _build_search_bar(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=1, column=0, sticky="ew", padx=32, pady=(16, 0))
        wrap.grid_columnconfigure(0, weight=1)

        self._search_frame = ctk.CTkFrame(
            wrap, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        self._search_frame.grid(row=0, column=0, sticky="ew")
        self._search_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self._search_frame, text="ARA",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T["text_muted"], width=50
        ).grid(row=0, column=0, padx=(16, 0), pady=14)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search_typed)

        self.entry_search = ctk.CTkEntry(
            self._search_frame, textvariable=self.search_var,
            font=ctk.CTkFont(size=14),
            fg_color="transparent", border_width=0,
            text_color=T["text_primary"],
            placeholder_text="Dosya adi veya icerik ara...",
            placeholder_text_color=T["text_muted"]
        )
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=(4, 16), pady=14)

        # Focus: gold border
        self.entry_search.bind("<FocusIn>",
            lambda e: self._search_frame.configure(border_color=T["gold"]))
        self.entry_search.bind("<FocusOut>",
            lambda e: self._search_frame.configure(border_color=T["border"]))

        self.lbl_search_time = ctk.CTkLabel(
            self._search_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=T["text_muted"], width=80
        )
        self.lbl_search_time.grid(row=0, column=2, padx=(0, 16), pady=14)

    # ── MAIN AREA (TABS) ────────────────────────────────

    def _build_main_area(self):
        self.tabs = ctk.CTkTabview(
            self, fg_color=T["bg"],
            segmented_button_fg_color=T["surface"],
            segmented_button_selected_color=T["surface2"],
            segmented_button_selected_hover_color=T["surface2"],
            segmented_button_unselected_color=T["surface"],
            segmented_button_unselected_hover_color=T["hover"],
            text_color=T["text_secondary"],
            text_color_disabled=T["text_muted"],
            corner_radius=8
        )
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=32, pady=(12, 0))

        self._build_results_tab(self.tabs.add("Sonuclar"))
        self._build_folders_tab(self.tabs.add("Klasorler"))
        self._build_about_tab(self.tabs.add("Hakkinda"))

    # ── RESULTS TAB ──────────────────────────────────────

    def _build_results_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Result count
        self.lbl_result_count = ctk.CTkLabel(
            parent, text="Arama yapmak icin yukardaki kutuyu kullanin",
            font=ctk.CTkFont(size=12), text_color=T["text_muted"], anchor="w"
        )
        self.lbl_result_count.grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Treeview Card — surface bg + border = depth
        tree_card = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        tree_card.grid(row=1, column=0, sticky="nsew")
        tree_card.grid_columnconfigure(0, weight=1)
        tree_card.grid_rowconfigure(0, weight=1)

        # Treeview style — design system colors
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("V.Treeview",
            background=T["surface"],
            foreground=T["text_primary"],
            fieldbackground=T["surface"],
            font=("Segoe UI", 10),
            rowheight=34,
            borderwidth=0)
        style.configure("V.Treeview.Heading",
            background=T["surface2"],
            foreground=T["text_secondary"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=0, relief="flat")
        style.map("V.Treeview",
            background=[("selected", "#2A2518")],    # Warm gold-tinted select
            foreground=[("selected", T["gold_light"])])
        style.layout("V.Treeview", [
            ("V.Treeview.treearea", {"sticky": "nswe"})
        ])

        cols = ("filename", "snippet", "directory", "ext", "size")
        self.tree = ttk.Treeview(
            tree_card, columns=cols, show="headings",
            selectmode="browse", style="V.Treeview"
        )

        self.tree.heading("filename", text="Dosya Adi")
        self.tree.heading("snippet", text="Eslesme")
        self.tree.heading("directory", text="Konum")
        self.tree.heading("ext", text="Tur")
        self.tree.heading("size", text="Boyut")

        self.tree.column("filename", width=180, minwidth=100)
        self.tree.column("snippet", width=300, minwidth=150)
        self.tree.column("directory", width=280, minwidth=120)
        self.tree.column("ext", width=55, minwidth=35, anchor="center")
        self.tree.column("size", width=75, minwidth=45, anchor="e")

        # Hover tags
        self.tree.tag_configure("hover",
            background=T["hover"], foreground=T["gold_light"])
        self.tree.tag_configure("normal",
            background=T["surface"], foreground=T["text_primary"])

        scrollbar = ctk.CTkScrollbar(tree_card, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=2)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._open_file)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Motion>", self._on_tree_hover)
        self.tree.bind("<Leave>", self._on_tree_leave)

        # Context menu
        self.ctx_menu = tk.Menu(
            self, tearoff=0,
            bg=T["surface2"], fg=T["text_primary"],
            activebackground=T["hover"], activeforeground=T["gold"],
            font=("Segoe UI", 9), bd=0
        )
        self.ctx_menu.add_command(label="Dosyayi Ac", command=self._open_file)
        self.ctx_menu.add_command(label="Klasoru Ac", command=self._open_folder)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Yolu Kopyala", command=self._copy_path)

        # Preview Card
        preview_card = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"], height=140
        )
        preview_card.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        preview_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            preview_card, text="ONIZLEME",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T["text_muted"]
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(10, 0))

        self.txt_preview = ctk.CTkTextbox(
            preview_card, height=90,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=T["surface2"], text_color=T["text_secondary"],
            corner_radius=6, border_width=0, wrap="word"
        )
        self.txt_preview.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 10))
        self.txt_preview.configure(state="disabled")

    # ── FOLDERS TAB ──────────────────────────────────────

    def _build_folders_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Klasor Ekle",
            font=ctk.CTkFont(size=13),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_secondary"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=140, height=36, command=self._add_folder
        ).pack(side="left", padx=(0, 8))

        self.btn_scan = ctk.CTkButton(
            btn_frame, text="Taramayi Baslat",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=T["gold"], hover_color=T["gold_light"],
            text_color=T["bg"], corner_radius=6,
            width=160, height=36, command=self._scan_all
        )
        self.btn_scan.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Secili Klasoru Kaldir",
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color=T["hover"],
            text_color=T["error"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=160, height=36, command=self._remove_folder
        ).pack(side="right")

        # Folder list card
        list_card = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        list_card.grid(row=1, column=0, sticky="nsew")
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(0, weight=1)

        self.folder_listbox = tk.Listbox(
            list_card, font=("Consolas", 11),
            bg=T["surface"], fg=T["text_primary"],
            selectbackground="#2A2518",
            selectforeground=T["gold"],
            bd=0, highlightthickness=0,
            activestyle="none", relief="flat"
        )
        self.folder_listbox.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.folder_listbox.bind("<Motion>", self._on_folder_hover)
        self.folder_listbox.bind("<Leave>", self._on_folder_leave)

        # Progress
        prog_frame = ctk.CTkFrame(parent, fg_color="transparent")
        prog_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        prog_frame.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(
            prog_frame, fg_color=T["surface2"],
            progress_color=T["gold"], corner_radius=3, height=6
        )
        self.progress.grid(row=0, column=0, sticky="ew")
        self.progress.set(0)

        self.lbl_progress = ctk.CTkLabel(
            prog_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=T["text_muted"]
        )
        self.lbl_progress.grid(row=0, column=1, padx=(12, 0))

        self._refresh_folder_list()

    # ── ABOUT TAB (Card-based) ───────────────────────────

    def _build_about_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # ─── Top: Logo + Brand ───
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, pady=(24, 0))

        logo = self._load_logo(180)
        if logo:
            ctk.CTkLabel(top, text="", image=logo).pack(pady=(0, 12))

        ctk.CTkLabel(
            top, text="VASTARION SCANNER",
            font=ctk.CTkFont(family="Georgia", size=20, weight="bold"),
            text_color=T["gold"]
        ).pack(pady=(0, 2))

        ctk.CTkLabel(
            top, text="File Intelligence Engine",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color=T["text_muted"]
        ).pack(pady=(0, 8))

        tk.Canvas(top, width=60, height=1, bg=T["gold_dim"], highlightthickness=0).pack(pady=(0, 12))

        ctk.CTkLabel(
            top,
            text="Bilgisayarinizdaki dosyalari hizlica bulmaniz icin tasarlandi.\n"
                 "Word, Excel, PDF ve Metin dosyalarinin icini okur\n"
                 "ve saniyeler icinde arama yapmanizi saglar.",
            font=ctk.CTkFont(size=13),
            text_color=T["text_secondary"], justify="center"
        ).pack()

        # ─── Bottom: Stats Cards ───
        stats_scroll = ctk.CTkFrame(parent, fg_color="transparent")
        stats_scroll.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        stats_scroll.grid_columnconfigure(0, weight=1)
        stats_scroll.grid_rowconfigure(0, weight=1)

        self.info_text = ctk.CTkTextbox(
            stats_scroll, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=T["surface"], text_color=T["text_secondary"],
            corner_radius=8, border_width=1, border_color=T["border"],
            wrap="word"
        )
        self.info_text.grid(row=0, column=0, sticky="nsew")
        self.info_text.configure(state="disabled")

        ctk.CTkButton(
            parent, text="Istatistikleri Yenile",
            font=ctk.CTkFont(size=12),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_secondary"], corner_radius=6,
            width=160, height=32, command=self._update_stats
        ).grid(row=2, column=0, pady=(8, 4))

    # ── STATUS BAR ───────────────────────────────────────

    def _build_status_bar(self):
        status = ctk.CTkFrame(
            self, fg_color=T["surface"], corner_radius=0, height=34
        )
        status.grid(row=3, column=0, sticky="ew")
        status.grid_propagate(False)
        status.grid_columnconfigure(1, weight=1)

        # Left: logo + status text
        left = ctk.CTkFrame(status, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=(24, 0), pady=4)

        logo_s = self._load_logo(18)
        if logo_s:
            ctk.CTkLabel(left, text="", image=logo_s).pack(side="left", padx=(0, 8))

        self.lbl_status = ctk.CTkLabel(
            left, text="Hazir",
            font=ctk.CTkFont(size=11), text_color=T["text_muted"], anchor="w"
        )
        self.lbl_status.pack(side="left")

        # Right: watcher
        self.lbl_watcher = ctk.CTkLabel(
            status, text="● Watcher aktif",
            font=ctk.CTkFont(size=11),
            text_color=T["success"], anchor="e"
        )
        self.lbl_watcher.grid(row=0, column=2, sticky="e", padx=(0, 24), pady=4)

    # ══════════════════════════════════════════════════════
    # SEARCH
    # ══════════════════════════════════════════════════════

    def _on_search_typed(self, *args):
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._execute_search)

    def _execute_search(self):
        query = self.search_var.get().strip()
        self.tree.delete(*self.tree.get_children())
        self._result_paths.clear()
        self._hover_item = None

        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.configure(state="disabled")

        if not query or len(query) < 2:
            self.lbl_result_count.configure(
                text="En az 2 karakter girin", text_color=T["text_muted"])
            self.lbl_search_time.configure(text="")
            return

        result = self.search_engine.search(query)
        self.lbl_search_time.configure(text=f"{result['elapsed_ms']} ms")

        if result["count"] == 0:
            self.lbl_result_count.configure(
                text=f'"{query}" icin sonuc bulunamadi', text_color=T["error"])
            return

        self.lbl_result_count.configure(
            text=f'"{query}" icin {result["count"]} sonuc', text_color=T["gold"])

        for r in result["results"]:
            size_str = format_size(r["size"]) if r["size"] else "-"
            snippet = r.get("snippet", "")[:80] or "(dosya adinda eslesme)"
            self.tree.insert("", "end", values=(
                r["filename"], snippet, r["directory"], r["ext"], size_str
            ), tags=("normal",))
            self._result_paths.append(r["filepath"])

    def _on_tree_select(self, event=None):
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")

        sel = self.tree.selection()
        if not sel:
            self.txt_preview.configure(state="disabled")
            return

        idx = self.tree.index(sel[0])
        if idx >= len(self._result_paths):
            self.txt_preview.configure(state="disabled")
            return

        filepath = self._result_paths[idx]
        query = self.search_var.get().strip()
        if not query:
            self.txt_preview.configure(state="disabled")
            return

        if filepath not in self._content_cache:
            content = extract_content(filepath) if os.path.exists(filepath) else ""
            self._content_cache[filepath] = content
            if len(self._content_cache) > 100:
                del self._content_cache[next(iter(self._content_cache))]

        content = self._content_cache.get(filepath, "")
        query_lower = tr_lower(query)

        # Highlight tag — eslesen kelime gold renkte
        try:
            self.txt_preview.tag_config(
                "highlight", foreground=T["gold"],
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"))
        except Exception:
            pass

        shown = 0
        for i, line in enumerate(content.split("\n")):
            if shown >= 8:
                break
            line_lower = tr_lower(line)
            if query_lower in line_lower:
                prefix = f"  Satir {i+1}: "
                line_text = line.strip()[:250]
                self.txt_preview.insert("end", prefix)

                # Eslesen kismi highlight ile ekle
                self._insert_highlighted(line_text, query)
                self.txt_preview.insert("end", "\n")
                shown += 1

        if shown == 0:
            self.txt_preview.insert("end", "  (Onizleme mevcut degil)")
        self.txt_preview.configure(state="disabled")

    def _insert_highlighted(self, text, query):
        """Metindeki eslesen kelimeleri gold renkte vurgular."""
        text_lower = tr_lower(text)
        query_lower = tr_lower(query)
        pos = 0
        while pos < len(text):
            idx = text_lower.find(query_lower, pos)
            if idx == -1:
                self.txt_preview.insert("end", text[pos:])
                break
            # Eslesmeden onceki kisim (normal)
            if idx > pos:
                self.txt_preview.insert("end", text[pos:idx])
            # Eslesen kisim (gold highlight)
            self.txt_preview.insert("end", text[idx:idx+len(query)], "highlight")
            pos = idx + len(query)

    # ── HOVER ────────────────────────────────────────────

    def _on_tree_hover(self, event):
        item = self.tree.identify_row(event.y)
        if item == self._hover_item:
            return
        if self._hover_item and self._hover_item not in self.tree.selection():
            self.tree.item(self._hover_item, tags=("normal",))
        self._hover_item = item
        if item and item not in self.tree.selection():
            self.tree.item(item, tags=("hover",))

    def _on_tree_leave(self, event):
        if self._hover_item and self._hover_item not in self.tree.selection():
            self.tree.item(self._hover_item, tags=("normal",))
        self._hover_item = None

    def _on_folder_hover(self, event):
        idx = self.folder_listbox.nearest(event.y)
        if idx == self._folder_hover_idx:
            return
        if self._folder_hover_idx is not None:
            try:
                self.folder_listbox.itemconfig(
                    self._folder_hover_idx, bg=T["surface"], fg=T["text_primary"])
            except tk.TclError:
                pass
        self._folder_hover_idx = idx
        if 0 <= idx < self.folder_listbox.size():
            self.folder_listbox.itemconfig(idx, bg=T["hover"], fg=T["gold_light"])

    def _on_folder_leave(self, event):
        if self._folder_hover_idx is not None:
            try:
                self.folder_listbox.itemconfig(
                    self._folder_hover_idx, bg=T["surface"], fg=T["text_primary"])
            except tk.TclError:
                pass
            self._folder_hover_idx = None

    # ── FILE OPERATIONS ──────────────────────────────────

    def _get_selected_path(self):
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        return self._result_paths[idx] if idx < len(self._result_paths) else None

    def _open_file(self, event=None):
        path = self._get_selected_path()
        if path and os.path.exists(path):
            os.startfile(path) if sys.platform == "win32" else os.system(f'xdg-open "{path}"')

    def _open_folder(self):
        path = self._get_selected_path()
        if path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                os.startfile(folder) if sys.platform == "win32" else os.system(f'xdg-open "{folder}"')

    def _copy_path(self):
        path = self._get_selected_path()
        if path:
            self.clipboard_clear()
            self.clipboard_append(path)
            self.lbl_status.configure(text=f"Kopyalandi: {path}")

    def _show_context_menu(self, event):
        try:
            self.tree.selection_set(self.tree.identify_row(event.y))
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx_menu.grab_release()

    # ── FOLDER MANAGEMENT ────────────────────────────────

    def _add_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Taranacak klasoru secin")
        if folder:
            self.db.add_watched_dir(folder)
            self._refresh_folder_list()
            self.lbl_status.configure(text=f"Eklendi: {folder}")

    def _remove_folder(self):
        sel = self.folder_listbox.curselection()
        if not sel:
            return
        self.db.remove_watched_dir(self.folder_listbox.get(sel[0]))
        self._refresh_folder_list()
        self.lbl_status.configure(text="Klasor kaldirildi.")

    def _refresh_folder_list(self):
        self.folder_listbox.delete(0, "end")
        for d in self.db.get_watched_dirs():
            self.folder_listbox.insert("end", d)

    def _scan_all(self):
        dirs = self.db.get_watched_dirs()
        if not dirs:
            self.lbl_status.configure(text="Taranacak klasor bulunamadi.")
            return
        if self.worker.is_running:
            return
        self.btn_scan.configure(text="Taraniyor...", state="disabled")
        self.progress.set(0)
        self.worker.start(dirs)

    # ── QUEUE ────────────────────────────────────────────

    def _process_queue(self):
        try:
            while True:
                msg_type, data = self.ui_queue.get_nowait()
                if msg_type == "status":
                    self.lbl_status.configure(text=data)
                elif msg_type == "progress":
                    indexed, total, skipped = data
                    self.progress.set(indexed / max(total, 1))
                    self.lbl_progress.configure(text=f"{indexed}/{total}")
                    self.lbl_status.configure(
                        text=f"Taraniyor: {indexed}/{total} | {skipped} atlandi")
                elif msg_type == "done":
                    indexed, total, skipped = data
                    self.lbl_status.configure(
                        text=f"Tamamlandi: {indexed} dosya, {skipped} atlandi")
                    self.progress.set(1)
                    self.lbl_progress.configure(text="Bitti")
                    self._update_stats()
                elif msg_type == "all_done":
                    self.btn_scan.configure(text="Taramayi Baslat", state="normal")
                    self._content_cache.clear()
                    self._update_stats()
                elif msg_type == "watcher_update":
                    self._update_stats()
                elif msg_type == "error":
                    self.lbl_status.configure(text=f"Hata: {data}")
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    # ── STATS ────────────────────────────────────────────

    def _update_stats(self):
        stats = self.db.get_stats()
        total = stats["total"]
        dirs_count = len(self.db.get_watched_dirs())

        self.lbl_stats.configure(text=f"{total:,} dosya indekslendi")

        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")

        # Card-style stats (CLI hissi yok)
        self.info_text.insert("end", "\n")
        self.info_text.insert("end", "   INDEX STATISTICS\n\n")
        self.info_text.insert("end", f"   Toplam Dosya          {total:,}\n")
        self.info_text.insert("end", f"   Izlenen Klasor        {dirs_count}\n")
        self.info_text.insert("end", f"   Watcher               Aktif (30s)\n")
        self.info_text.insert("end", f"   Veritabani            {self.db.db_path}\n")

        if stats["by_extension"]:
            self.info_text.insert("end", "\n\n   FILE DISTRIBUTION\n\n")
            max_c = max(stats["by_extension"].values(), default=1)
            for ext, count in sorted(stats["by_extension"].items(), key=lambda x: -x[1]):
                bar_len = int(count / max(max_c, 1) * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                pct = count / max(total, 1) * 100
                self.info_text.insert("end",
                    f"   {ext:8s}  {bar}  {count:>5,}  ({pct:.1f}%)\n")

        self.info_text.configure(state="disabled")

    # ── CLEANUP ──────────────────────────────────────────

    def _on_close(self):
        log.info("Uygulama kapatiliyor")
        self.worker.stop()
        self.watcher.stop()
        self.db.close()
        self.destroy()
