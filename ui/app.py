import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from datetime import datetime

from config import (
    THEME_DARK, THEME_LIGHT, APP_NAME, APP_VERSION,
    get_active_theme_mode, set_theme_mode, get_active_theme,
    ORGANIZER_TEMPLATES
)
from db.database import Database
from core.search import SearchEngine
from core.worker import IndexWorker
from core.watcher import FileWatcher
from core.parsers import extract_content
from core.organizer import FileOrganizer, OrganizerRule, MIN_SCORE_THRESHOLD
from utils.file_utils import format_size
from utils.text_utils import tr_lower
from logger import log


class VastarionApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        # Tema — başlangıçta doğru modu ayarla
        self._theme_mode = get_active_theme_mode()
        self.T = THEME_DARK if self._theme_mode == "dark" else THEME_LIGHT
        ctk.set_appearance_mode("dark" if self._theme_mode == "dark" else "light")

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1200x800")
        self.minsize(950, 650)
        self.configure(fg_color=self.T["bg"])

        self._set_icon()

        # Core
        self.ui_queue = queue.Queue()
        self.db = Database()
        self.search_engine = SearchEngine(self.db)
        self.worker = IndexWorker(self.db, self.ui_queue)
        self.watcher = FileWatcher(self.db)
        self.watcher.on_change(lambda n: self.ui_queue.put(("watcher_update", n)))
        self.watcher.start()

        # Organizer
        self.organizer = FileOrganizer(self.db, self.ui_queue)

        self._search_after_id = None
        self._content_cache = {}
        self._result_paths = []
        self._all_results = []       # Lazy loading: tum sonuclar
        self._loaded_count = 0       # Lazy loading: yuklenmiş sayisi
        self._LAZY_BATCH = 50        # Lazy loading: her seferde yuklenecek
        self._search_history = []    # Arama gecmisi (son 20)
        self._hover_item = None
        self._folder_hover_idx = None
        self._logo_refs = {}

        # Organizer state
        self._org_rule_widgets = []
        self._org_target_dir = ctk.StringVar(value="")
        self._org_include_unmatched = ctk.BooleanVar(value=True)

        self._themable = []

        self._build_ui()
        self._process_queue()
        self._update_stats()
        self._apply_ctk_mode()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # Helpers

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

    def _apply_ctk_mode(self):
        """CustomTkinter appearance mode'u ayarlar."""
        ctk.set_appearance_mode("dark" if self._theme_mode == "dark" else "light")

    # THEME TOGGLE — Async, donma yok

    def _themable_add(self, widget, role: str, **extras):
        """Widget'i themable registry'ye ekler.

        role: 'primary_btn', 'ghost_btn', 'danger_btn', 'label_primary',
              'label_secondary', 'label_muted', 'label_gold',
              'canvas_gold', 'canvas_bg', 'checkbox', 'scrollable_frame',
              'scrollbar'
        extras: ileride ihtiyac olursa ek bilgi (ornek: 'hover_keeps_default')
        """
        self._themable.append({"widget": widget, "role": role, **extras})
        return widget

    def _toggle_theme(self):
        """Dark <-> Light tema gecisi — Senkron, tek seferde.

        Strateji:
        1. Eski->Yeni renk haritasi cikar (ornek: dark surface -> light surface).
        2. ctk.set_appearance_mode cagir — CTk built-in widget'lar (scrollbar,
           checkbox, sekme baslik canvasi) icin sart.
        3. Named widget'lara ozel renkleri uygula (_refresh_all_theme).
        4. Tum widget agacini gezip ESKI tema rengini gordugumu YENI tema rengiyle
           degistir — boylece Duzenle sekmesi icin tabview lazy-render eden tum
           gizli widget'lar da yakalanir.
        5. Tek update_idletasks ile sonra repaint et.
        """
        if not hasattr(self, "btn_theme"):
            return

        new_mode = "light" if self._theme_mode == "dark" else "dark"

        # Eski tema sozlugu (renk haritasi icin lazim)
        T_old = THEME_DARK if self._theme_mode == "dark" else THEME_LIGHT
        T_new = THEME_LIGHT if new_mode == "light" else THEME_DARK

        # Eski renkleri yeni renklere maple
        # Hem string -> string hem CTk'nin (light, dark) tuple varyasyonu
        color_map = {}
        for k in T_old:
            if k in T_new and T_old[k] != T_new[k]:
                color_map[T_old[k].lower()] = T_new[k]

        # Treeview seleksiyon arka planlari (hardcoded olarak gecen renkler)
        if new_mode == "light":
            color_map["#3a3220"] = "#E8D9A8"
            color_map["#2a2518"] = "#E8D9A8"
        else:
            color_map["#e8d9a8"] = "#3A3220"
            color_map["#f0e8d0"] = "#3A3220"

        # State'i guncelle
        self._theme_mode = new_mode
        self.T = T_new
        set_theme_mode(new_mode)

        # CTk built-in widget mode (scrollbar arrows, checkbox marks, segment headers)
        try:
            ctk.set_appearance_mode(new_mode)
        except Exception as e:
            log.warning(f"set_appearance_mode hatasi: {e}")

        # Bizim ozel renklerimizi named widget'lara uygula
        self._refresh_all_theme()

        # Safety net: tum widget agacini gezip eski-yeni renk remap
        # (CTkTabview lazy-render'inde gozden kacanlari yakalar)
        try:
            self._sweep_widget_tree(self, color_map)
        except Exception as e:
            log.warning(f"Widget tree sweep hatasi: {e}")

        # Buton ikonu
        icon = "☀" if new_mode == "dark" else "🌙"
        self.btn_theme.configure(text=icon, text_color=T_new["text_primary"])

        # Tek seferlik repaint
        self.update_idletasks()

    def _sweep_widget_tree(self, root, color_map):
        """Widget agacini recursive gezerek eski tema renklerini yenisine cevirir.

        CTkFrame/CTkLabel/CTkButton widget'larin fg_color, text_color,
        border_color, hover_color gibi propertylerini cget ile okur, eski
        tema renginin haritasinda varsa yenisine configure eder.

        Bu, CTkTabview gibi lazy-render eden widget'lardaki gizli iceriklerin
        de tema gecisinde guncellenmesini saglar.
        """
        # CTk widget'lar bu propertyleri tasiyabilir
        props = ("fg_color", "text_color", "border_color", "hover_color",
                 "progress_color", "placeholder_text_color",
                 "checkmark_color", "button_color", "button_hover_color",
                 "selected_color", "selected_hover_color",
                 "unselected_color", "unselected_hover_color",
                 "scrollbar_button_color", "scrollbar_button_hover_color")

        def _remap_value(val):
            """Tek bir renk degerini haritada arar."""
            if isinstance(val, str):
                lo = val.lower()
                if lo in color_map:
                    return color_map[lo]
            elif isinstance(val, (list, tuple)) and len(val) == 2:
                # CTk (light, dark) tuple varyasyonu
                a = val[0].lower() if isinstance(val[0], str) else None
                b = val[1].lower() if isinstance(val[1], str) else None
                new_a = color_map.get(a) if a else None
                new_b = color_map.get(b) if b else None
                if new_a or new_b:
                    return (new_a or val[0], new_b or val[1])
            return None

        def _walk(w):
            # tk.Canvas ve tk.Listbox icin bg attribute farkli (CTk degil)
            try:
                if isinstance(w, tk.Canvas):
                    cur = w.cget("bg")
                    new = _remap_value(cur)
                    if new and isinstance(new, str):
                        w.configure(bg=new)
            except Exception:
                pass

            # CTkScrollableFrame icin ozel patch: ic _parent_canvas
            if isinstance(w, ctk.CTkScrollableFrame):
                try:
                    cur_fg = w.cget("fg_color")
                    target = _remap_value(cur_fg) or self.T["surface"]
                    if isinstance(target, (list, tuple)):
                        target = target[0] if self._theme_mode == "light" else target[1]
                    self._patch_scrollable_canvas(w, target)
                except Exception:
                    pass

            # CTk widget'lar
            for prop in props:
                try:
                    cur = w.cget(prop)
                except Exception:
                    continue
                new = _remap_value(cur)
                if new is not None:
                    try:
                        w.configure(**{prop: new})
                    except Exception:
                        pass

            # Cocuk widget'lara in
            try:
                for child in w.winfo_children():
                    _walk(child)
            except Exception:
                pass

        _walk(root)

    def _refresh_all_theme(self):
        """Tum widget'lari ve stilleri yeni temaya gore gunceller.

        Iki asama:
        1. Sabit (named) widget'lar: kart frame'leri, treeview, listbox vs.
        2. Registry uzerinden inline widget'lar: butonlar, label'lar, canvas'lar.

        Hata yakalama her widget icin ayri — bir widget destroy edilmis olsa
        bile diger guncelleme zinciri kirilmaz.
        """
        T = self.T
        treeview_select_bg = "#3A3220" if self._theme_mode == "dark" else "#E8D9A8"

        # Named (sabit) widget'lar

        # Ana pencere
        self.configure(fg_color=T["bg"])

        # Header
        self._safe(self._header_frame, fg_color=T["bg"])
        self._safe(self.lbl_stats, text_color=T["text_muted"])

        # Search bar (entry'nin fg_color'una DOKUNMA — transparent)
        self._safe(self._search_frame, fg_color=T["surface"], border_color=T["border"])
        self._safe(self.entry_search,
            text_color=T["text_primary"],
            placeholder_text_color=T["text_muted"])
        self._safe(self._btn_history,
            hover_color=T["hover"], text_color=T["text_muted"])
        self._safe(self.lbl_search_time, text_color=T["text_muted"])

        # Tabs
        self._safe(self.tabs,
            fg_color=T["bg"],
            segmented_button_fg_color=T["surface"],
            segmented_button_selected_color=T["surface2"],
            segmented_button_selected_hover_color=T["surface2"],
            segmented_button_unselected_color=T["surface"],
            segmented_button_unselected_hover_color=T["hover"],
            text_color=T["text_secondary"],
            text_color_disabled=T["text_muted"]
        )
        for tab_name in ["Sonuclar", "Klasorler", "Duzenle", "Hakkinda"]:
            try:
                self.tabs.tab(tab_name).configure(fg_color=T["bg"])
            except Exception:
                pass

        # Sonuclar sekmesi: kartlar
        self._safe(self._tree_card, fg_color=T["surface"], border_color=T["border"])
        self._safe(self._preview_card, fg_color=T["surface"], border_color=T["border"])
        self._safe(self._folder_list_card, fg_color=T["surface"], border_color=T["border"])

        # ttk Treeview stilleri (V + Org)
        self._apply_treeview_styles(treeview_select_bg)

        # Result count + Preview
        self._safe(self.lbl_result_count, text_color=T["text_muted"])
        self._safe(self.txt_preview,
            fg_color=T["surface2"], text_color=T["text_secondary"])

        # Treeview tag'leri
        try:
            self.tree.tag_configure("hover",
                background=T["hover"], foreground=T["gold_light"])
            self.tree.tag_configure("normal",
                background=T["surface"], foreground=T["text_primary"])
        except Exception:
            pass

        # Folder listbox (tk.Listbox — CTk degil)
        try:
            self.folder_listbox.configure(
                bg=T["surface"], fg=T["text_primary"],
                selectbackground=treeview_select_bg,
                selectforeground=T["gold"])
        except Exception:
            pass

        # Scan butonu + Progress
        self._safe(self.btn_scan,
            fg_color=T["gold"], hover_color=T["gold_light"], text_color=T["bg"])
        self._safe(self.progress,
            fg_color=T["surface2"], progress_color=T["gold"])
        self._safe(self.lbl_progress, text_color=T["text_muted"])

        # Context menu (tk.Menu)
        try:
            self.ctx_menu.configure(
                bg=T["surface2"], fg=T["text_primary"],
                activebackground=T["hover"], activeforeground=T["gold"])
        except Exception:
            pass

        # Status bar
        self._safe(self._status_frame, fg_color=T["surface"])
        self._safe(self.lbl_status, text_color=T["text_muted"])
        self._safe(self.lbl_watcher, text_color=T["success"])

        # About tab
        self._safe(self.info_text,
            fg_color=T["surface"], text_color=T["text_secondary"],
            border_color=T["border"])

        # Organizer sekmesi (named widget'lar)
        self._refresh_organizer_theme()

        # Registry: inline olusturulmus widget'lar
        self._apply_registry_theme()

    def _safe(self, widget, **kwargs):
        """Widget configure'u guvenli sar — destroy edilmiş widget'larda hata yutar."""
        try:
            widget.configure(**kwargs)
        except Exception:
            pass

    def _patch_scrollable_canvas(self, scrollable_frame, color):
        """CTkScrollableFrame'in ic tk.Canvas ve ic frame'ini elle renklendirir.

        CTkScrollableFrame'in _parent_canvas (tk.Canvas) attribute'u CTk tarafindan
        yonetilir ama appearance_mode degisiminde her zaman dogru renge gecmez.
        Bu yuzden referansa erisip dogrudan bg ayarliyoruz.
        """
        for attr in ("_parent_canvas", "_scrollbar"):
            inner = getattr(scrollable_frame, attr, None)
            if inner is not None:
                try:
                    if isinstance(inner, tk.Canvas):
                        inner.configure(bg=color, highlightthickness=0)
                    else:
                        inner.configure(fg_color=color)
                except Exception:
                    pass

    def _apply_treeview_styles(self, treeview_select_bg):
        """Tum ttk.Treeview stillerini (V ve Org) yeni temaya uyarlar."""
        T = self.T
        style = ttk.Style()
        for style_name in ("V.Treeview", "Org.Treeview"):
            try:
                style.configure(style_name,
                    background=T["surface"], foreground=T["text_primary"],
                    fieldbackground=T["surface"])
                style.configure(f"{style_name}.Heading",
                    background=T["surface2"], foreground=T["text_secondary"])
                style.map(style_name,
                    background=[("selected", treeview_select_bg)],
                    foreground=[("selected", T["gold_light"])])
            except Exception:
                pass

    def _apply_registry_theme(self):
        """Registry'deki inline widget'lari role'lerine gore boyar."""
        T = self.T
        for entry in self._themable:
            w = entry.get("widget")
            role = entry.get("role")
            if w is None:
                continue
            try:
                if not w.winfo_exists():
                    continue
            except Exception:
                continue

            try:
                if role == "primary_btn":
                    w.configure(
                        fg_color=T["gold"], hover_color=T["gold_light"],
                        text_color=T["bg"])
                elif role == "ghost_btn":
                    w.configure(
                        fg_color=T["surface2"], hover_color=T["hover"],
                        text_color=T["text_secondary"], border_color=T["border"])
                elif role == "ghost_btn_gold":
                    w.configure(
                        fg_color=T["surface2"], hover_color=T["hover"],
                        text_color=T["gold"], border_color=T["border"])
                elif role == "ghost_btn_primary_text":
                    w.configure(
                        fg_color=T["surface2"], hover_color=T["hover"],
                        text_color=T["text_primary"], border_color=T["border"])
                elif role == "danger_btn":
                    w.configure(
                        fg_color="transparent", hover_color=T["hover"],
                        text_color=T["error"], border_color=T["border"])
                elif role == "danger_btn_borderless":
                    w.configure(
                        fg_color="transparent", hover_color=T["hover"],
                        text_color=T["error"])
                elif role == "label_primary":
                    w.configure(text_color=T["text_primary"])
                elif role == "label_secondary":
                    w.configure(text_color=T["text_secondary"])
                elif role == "label_muted":
                    w.configure(text_color=T["text_muted"])
                elif role == "label_gold":
                    w.configure(text_color=T["gold"])
                elif role == "canvas_gold":
                    # tk.Canvas — gold cizgiler
                    w.configure(bg=T["gold"])
                elif role == "canvas_gold_dim":
                    w.configure(bg=T["gold_dim"])
                elif role == "canvas_bg":
                    w.configure(bg=T["bg"])
                elif role == "checkbox":
                    w.configure(
                        text_color=T["text_secondary"],
                        fg_color=T["gold"], hover_color=T["gold_light"],
                        checkmark_color=T["bg"])
                elif role == "scrollable_frame":
                    # CTkScrollableFrame — fg_color="transparent" varsayim
                    w.configure(fg_color="transparent")
                elif role == "transparent_frame":
                    w.configure(fg_color="transparent")
            except Exception:
                # Bir widget'in configure'i basarisiz olsa bile devam et
                pass

    def _refresh_organizer_theme(self):
        """Organizer sekmesinin sabit (named) widget'larini gunceller."""
        T = self.T
        try:
            self._safe(self._org_target_frame,
                fg_color=T["surface"], border_color=T["border"])
            self._safe(self._org_target_entry,
                text_color=T["text_primary"],
                placeholder_text_color=T["text_muted"])
            self._safe(self._org_btn_select,
                fg_color=T["gold"], hover_color=T["gold_light"],
                text_color=T["bg"])
            self._safe(self._org_rules_scroll_frame,
                fg_color=T["surface"], border_color=T["border"])
            # CTkScrollableFrame ic canvas'ini da elle guncelle
            if hasattr(self, "_org_rules_scrollable"):
                self._safe(self._org_rules_scrollable, fg_color=T["surface"])
                self._patch_scrollable_canvas(self._org_rules_scrollable, T["surface"])
            self._safe(self._org_preview_frame,
                fg_color=T["surface"], border_color=T["border"])
            self._safe(self._org_progress_bar,
                fg_color=T["surface2"], progress_color=T["gold"])
            self._safe(self._org_status_label, text_color=T["text_muted"])

            self._safe(self._org_btn_preview,
                fg_color=T["surface2"], hover_color=T["hover"],
                text_color=T["text_primary"], border_color=T["border"])
            self._safe(self._org_btn_execute,
                fg_color=T["gold"], hover_color=T["gold_light"],
                text_color=T["bg"])

            # Kural widget'lari
            for widgets in self._org_rule_widgets:
                self._safe(widgets["frame"],
                    fg_color=T["surface2"], border_color=T["border"])
                self._safe(widgets["folder_entry"],
                    fg_color=T["surface"], text_color=T["text_primary"],
                    border_color=T["border"],
                    placeholder_text_color=T["text_muted"])
                self._safe(widgets["keywords_entry"],
                    fg_color=T["surface"], text_color=T["text_primary"],
                    border_color=T["border"],
                    placeholder_text_color=T["text_muted"])
                # Etiketler ve sil butonu (varsa)
                for k in ("num_label", "folder_label", "kw_label"):
                    if k in widgets:
                        self._safe(widgets[k], text_color=T["gold"] if k == "num_label" else T["text_muted"])
                if "del_btn" in widgets:
                    self._safe(widgets["del_btn"],
                        fg_color="transparent", hover_color=T["hover"],
                        text_color=T["error"])

            # Empty label
            if hasattr(self, "_org_empty_label"):
                self._safe(self._org_empty_label, text_color=T["text_secondary"])

            self._update_org_confidence_tags()

        except Exception:
            pass

    # BUILD UI

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)   # main area expands

        self._build_header()       # row 0
        self._build_search_bar()   # row 1
        self._build_main_area()    # row 2
        self._build_status_bar()   # row 3

    # HEADER

    def _build_header(self):
        T = self.T
        self._header_frame = ctk.CTkFrame(self, fg_color=T["bg"], corner_radius=0, height=120)
        self._header_frame.grid(row=0, column=0, sticky="ew")
        self._header_frame.grid_columnconfigure(1, weight=1)
        self._header_frame.grid_propagate(False)

        # Brand: Logo + Text
        brand = ctk.CTkFrame(self._header_frame, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w", padx=32, pady=16)

        logo = self._load_logo(100)
        if logo:
            ctk.CTkLabel(brand, text="", image=logo).pack(side="left", padx=(0, 20))

        text_block = ctk.CTkFrame(brand, fg_color="transparent")
        text_block.pack(side="left", anchor="s", pady=(0, 4))

        scanner_lbl = ctk.CTkLabel(
            text_block, text="Scanner",
            font=ctk.CTkFont(family="Georgia", size=24, slant="italic"),
            text_color=T["gold"]
        )
        scanner_lbl.pack(anchor="w")
        self._themable_add(scanner_lbl, "label_gold")

        # Ince gold cizgi (nav-logo::after efekti)
        gold_line = tk.Canvas(
            text_block, width=40, height=1, bg=T["gold"], highlightthickness=0
        )
        gold_line.pack(anchor="w", pady=(3, 5))
        self._themable_add(gold_line, "canvas_gold")

        engine_lbl = ctk.CTkLabel(
            text_block, text="File Intelligence Engine",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=T["text_muted"]
        )
        engine_lbl.pack(anchor="w")
        self._themable_add(engine_lbl, "label_muted")

        # Sağ: Stats + Theme Toggle
        right_frame = ctk.CTkFrame(self._header_frame, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="e", padx=32)

        self.lbl_stats = ctk.CTkLabel(
            right_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=T["text_muted"]
        )
        self.lbl_stats.pack(side="left", padx=(0, 16))

        # Tema toggle butonu
        theme_icon = "☀" if self._theme_mode == "dark" else "🌙"
        self.btn_theme = ctk.CTkButton(
            right_frame, text=theme_icon,
            font=ctk.CTkFont(size=18),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["gold"], corner_radius=8,
            width=42, height=42,
            command=self._toggle_theme
        )
        self.btn_theme.pack(side="left")

        # Theme toggle (alanini registry'ye eklemiyoruz — _refresh_all_theme zaten elden gecirir)

        # Border bottom
        border_canvas = tk.Canvas(
            self._header_frame, height=1, bg=T["bg"], highlightthickness=0
        )
        border_canvas.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._themable_add(border_canvas, "canvas_bg")

    # SEARCH BAR

    def _build_search_bar(self):
        T = self.T
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=1, column=0, sticky="ew", padx=32, pady=(16, 0))
        wrap.grid_columnconfigure(0, weight=1)

        self._search_frame = ctk.CTkFrame(
            wrap, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        self._search_frame.grid(row=0, column=0, sticky="ew")
        self._search_frame.grid_columnconfigure(1, weight=1)

        lbl_ara = ctk.CTkLabel(
            self._search_frame, text="ARA",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T["text_muted"], width=50
        )
        lbl_ara.grid(row=0, column=0, padx=(16, 0), pady=14)
        self._themable_add(lbl_ara, "label_muted")

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
            lambda e: self._search_frame.configure(border_color=self.T["gold"]))
        self.entry_search.bind("<FocusOut>",
            lambda e: self._search_frame.configure(border_color=self.T["border"]))

        # Arama gecmisi butonu
        self._btn_history = ctk.CTkButton(
            self._search_frame, text="▼",
            font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color=T["hover"],
            text_color=T["text_muted"], width=28, height=28,
            corner_radius=4, command=self._show_search_history
        )
        self._btn_history.grid(row=0, column=2, padx=(0, 4), pady=14)

        self.lbl_search_time = ctk.CTkLabel(
            self._search_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=T["text_muted"], width=80
        )
        self.lbl_search_time.grid(row=0, column=3, padx=(0, 16), pady=14)

    # MAIN AREA (TABS)

    def _build_main_area(self):
        T = self.T
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
        self._build_organizer_tab(self.tabs.add("Duzenle"))
        self._build_about_tab(self.tabs.add("Hakkinda"))

    # RESULTS TAB

    def _build_results_tab(self, parent):
        T = self.T
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Üst satır: result count + export butonu
        top_row = ctk.CTkFrame(parent, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top_row.grid_columnconfigure(0, weight=1)

        self.lbl_result_count = ctk.CTkLabel(
            top_row, text="Arama yapmak icin yukardaki kutuyu kullanin",
            font=ctk.CTkFont(size=12), text_color=T["text_muted"], anchor="w"
        )
        self.lbl_result_count.grid(row=0, column=0, sticky="w")

        # CSV export butonu — sonuc varsa aktif olur
        self.btn_export_csv = ctk.CTkButton(
            top_row, text="⬇ CSV Disa Aktar",
            font=ctk.CTkFont(size=11),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_secondary"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=140, height=28, state="disabled",
            command=self._export_results_csv
        )
        self.btn_export_csv.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._themable_add(self.btn_export_csv, "ghost_btn")

        # Treeview Card — surface bg + border = depth
        self._tree_card = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        self._tree_card.grid(row=1, column=0, sticky="nsew")
        self._tree_card.grid_columnconfigure(0, weight=1)
        self._tree_card.grid_rowconfigure(0, weight=1)

        # Treeview style — design system colors
        style = ttk.Style()
        style.theme_use("clam")
        treeview_select_bg = "#2A2518" if self._theme_mode == "dark" else "#F0E8D0"
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
            background=[("selected", treeview_select_bg)],
            foreground=[("selected", T["gold_light"])])
        style.layout("V.Treeview", [
            ("V.Treeview.treearea", {"sticky": "nswe"})
        ])

        cols = ("filename", "snippet", "directory", "ext", "size")
        self.tree = ttk.Treeview(
            self._tree_card, columns=cols, show="headings",
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

        scrollbar = ctk.CTkScrollbar(self._tree_card, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._tree_scroll_handler)
        self._tree_scrollbar = scrollbar
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
        self._preview_card = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"], height=140
        )
        self._preview_card.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self._preview_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._preview_card, text="ONIZLEME",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T["text_muted"]
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(10, 0))

        self.txt_preview = ctk.CTkTextbox(
            self._preview_card, height=90,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=T["surface2"], text_color=T["text_secondary"],
            corner_radius=6, border_width=0, wrap="word"
        )
        self.txt_preview.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 10))
        self.txt_preview.configure(state="disabled")

    # FOLDERS TAB

    def _build_folders_tab(self, parent):
        T = self.T
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        btn_add_folder = ctk.CTkButton(
            btn_frame, text="Klasor Ekle",
            font=ctk.CTkFont(size=13),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_secondary"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=140, height=36, command=self._add_folder
        )
        btn_add_folder.pack(side="left", padx=(0, 8))
        self._themable_add(btn_add_folder, "ghost_btn")

        self.btn_scan = ctk.CTkButton(
            btn_frame, text="Taramayi Baslat",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=T["gold"], hover_color=T["gold_light"],
            text_color=T["bg"], corner_radius=6,
            width=160, height=36, command=self._scan_all
        )
        self.btn_scan.pack(side="left", padx=(0, 8))

        btn_remove_folder = ctk.CTkButton(
            btn_frame, text="Secili Klasoru Kaldir",
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color=T["hover"],
            text_color=T["error"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=160, height=36, command=self._remove_folder
        )
        btn_remove_folder.pack(side="right")
        self._themable_add(btn_remove_folder, "danger_btn")

        # Folder list card
        self._folder_list_card = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        self._folder_list_card.grid(row=1, column=0, sticky="nsew")
        self._folder_list_card.grid_columnconfigure(0, weight=1)
        self._folder_list_card.grid_rowconfigure(0, weight=1)

        treeview_select_bg = "#2A2518" if self._theme_mode == "dark" else "#F0E8D0"
        self.folder_listbox = tk.Listbox(
            self._folder_list_card, font=("Consolas", 11),
            bg=T["surface"], fg=T["text_primary"],
            selectbackground=treeview_select_bg,
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

    # ORGANIZER TAB — Dosya Düzenleme

    def _build_organizer_tab(self, parent):
        T = self.T
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)  # Kurallar bolumu genisler

        # Üst Bilgi
        info_label = ctk.CTkLabel(
            parent,
            text="📂  Dosyalarinizi iceriklerine gore otomatik olarak klasorlere ayirin.\n"
                 "     Kurallar tanimlayin, onizleyin, onaylayin — orijinal dosyalar yerinde kalir.",
            font=ctk.CTkFont(size=12),
            text_color=T["text_secondary"],
            justify="left", anchor="w"
        )
        info_label.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._themable_add(info_label, "label_secondary")

        # Hedef Klasör + Butonlar
        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        top_bar.grid_columnconfigure(1, weight=1)

        # Hedef klasör
        self._org_target_frame = ctk.CTkFrame(
            top_bar, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        self._org_target_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self._org_target_frame.grid_columnconfigure(1, weight=1)

        lbl_target = ctk.CTkLabel(
            self._org_target_frame, text="HEDEF KLASOR",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T["text_muted"], width=110
        )
        lbl_target.grid(row=0, column=0, padx=(16, 4), pady=10)
        self._themable_add(lbl_target, "label_muted")

        self._org_target_entry = ctk.CTkEntry(
            self._org_target_frame, textvariable=self._org_target_dir,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", border_width=0,
            text_color=T["text_primary"],
            placeholder_text="Duzenlenen dosyalar buraya kopyalanacak...",
            placeholder_text_color=T["text_muted"]
        )
        self._org_target_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=10)

        self._org_btn_select = ctk.CTkButton(
            self._org_target_frame, text="Sec",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=T["gold"], hover_color=T["gold_light"],
            text_color=T["bg"], corner_radius=6,
            width=70, height=32, command=self._org_select_target
        )
        self._org_btn_select.grid(row=0, column=2, padx=(8, 12), pady=10)

        # Butonlar satırı
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", pady=(8, 4))

        btn_template = ctk.CTkButton(
            btn_row, text="📋 Sablon Yukle",
            font=ctk.CTkFont(size=12),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_secondary"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=140, height=34, command=self._org_load_template
        )
        btn_template.pack(side="left", padx=(0, 6))
        self._themable_add(btn_template, "ghost_btn")

        btn_add_rule = ctk.CTkButton(
            btn_row, text="+ Kural Ekle",
            font=ctk.CTkFont(size=12),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["gold"], border_width=1,
            border_color=T["border"], corner_radius=6,
            width=120, height=34, command=self._org_add_rule
        )
        btn_add_rule.pack(side="left", padx=(0, 6))
        self._themable_add(btn_add_rule, "ghost_btn_gold")

        btn_clear = ctk.CTkButton(
            btn_row, text="Tumunu Temizle",
            font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color=T["hover"],
            text_color=T["error"], corner_radius=6,
            width=120, height=34, command=self._org_clear_rules
        )
        btn_clear.pack(side="left", padx=(0, 6))
        self._themable_add(btn_clear, "danger_btn_borderless")

        # Eşleşmeyenler checkbox
        cb_unmatched = ctk.CTkCheckBox(
            btn_row, text='Eslesmeyen dosyalari "Diger" klasorune kopyala',
            font=ctk.CTkFont(size=11),
            text_color=T["text_secondary"],
            fg_color=T["gold"], hover_color=T["gold_light"],
            checkmark_color=T["bg"],
            variable=self._org_include_unmatched
        )
        cb_unmatched.pack(side="right")
        self._themable_add(cb_unmatched, "checkbox")

        # Kurallar Listesi
        self._org_rules_scroll_frame = ctk.CTkFrame(
            parent, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"]
        )
        self._org_rules_scroll_frame.grid(row=3, column=0, sticky="nsew", pady=(4, 8))
        self._org_rules_scroll_frame.grid_columnconfigure(0, weight=1)
        self._org_rules_scroll_frame.grid_rowconfigure(0, weight=1)

        self._org_rules_scrollable = ctk.CTkScrollableFrame(
            self._org_rules_scroll_frame, fg_color=T["surface"],
            corner_radius=0
        )
        self._org_rules_scrollable.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._org_rules_scrollable.grid_columnconfigure(0, weight=1)

        # Başlangıç bilgi metni
        self._org_empty_label = ctk.CTkLabel(
            self._org_rules_scrollable,
            text="Henuz kural eklenmedi.\n\n"
                 "\"Sablon Yukle\" ile hazir kurallar yukleyebilir\n"
                 "veya \"+ Kural Ekle\" butonuyla kendiniz olusturabilirsiniz.",
            font=ctk.CTkFont(size=12),
            text_color=T["text_secondary"], justify="center"
        )
        self._org_empty_label.grid(row=0, column=0, pady=40)

        # Alt: Önizleme + Eylem
        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="ew", pady=(0, 0))
        bottom.grid_columnconfigure(0, weight=1)

        # Önizleme + Kopyalama butonları
        action_row = ctk.CTkFrame(bottom, fg_color="transparent")
        action_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self._org_btn_preview = ctk.CTkButton(
            action_row, text="🔍 Dosyalari Tara ve Onizle",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_primary"], border_width=1,
            border_color=T["border"], corner_radius=6,
            height=38, command=self._org_run_preview
        )
        self._org_btn_preview.pack(side="left", padx=(0, 8))

        self._org_btn_execute = ctk.CTkButton(
            action_row, text="✅ Duzenlemeyi Baslat",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=T["gold"], hover_color=T["gold_light"],
            text_color=T["bg"], corner_radius=6,
            height=38, state="disabled",
            command=self._org_run_execute
        )
        self._org_btn_execute.pack(side="left", padx=(0, 8))

        self._org_status_label = ctk.CTkLabel(
            action_row, text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=T["text_muted"]
        )
        self._org_status_label.pack(side="right")

        # Önizleme kartı
        self._org_preview_frame = ctk.CTkFrame(
            bottom, fg_color=T["surface"], corner_radius=8,
            border_width=1, border_color=T["border"], height=140
        )
        self._org_preview_frame.grid(row=1, column=0, sticky="ew")
        self._org_preview_frame.grid_columnconfigure(0, weight=1)
        self._org_preview_frame.grid_rowconfigure(0, weight=1)

        # Önizleme Treeview
        style = ttk.Style()
        treeview_select_bg = "#2A2518" if self._theme_mode == "dark" else "#F0E8D0"
        style.configure("Org.Treeview",
            background=T["surface"],
            foreground=T["text_primary"],
            fieldbackground=T["surface"],
            font=("Segoe UI", 10),
            rowheight=28,
            borderwidth=0)
        style.configure("Org.Treeview.Heading",
            background=T["surface2"],
            foreground=T["text_secondary"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=0, relief="flat")
        style.map("Org.Treeview",
            background=[("selected", treeview_select_bg)],
            foreground=[("selected", T["gold_light"])])

        org_cols = ("category", "filename", "confidence", "ext", "size")
        self._org_tree = ttk.Treeview(
            self._org_preview_frame, columns=org_cols, show="headings",
            selectmode="browse", style="Org.Treeview", height=5
        )

        self._org_tree.heading("category", text="Kategori")
        self._org_tree.heading("filename", text="Dosya Adi")
        self._org_tree.heading("confidence", text="Guvenilirlik")
        self._org_tree.heading("ext", text="Tur")
        self._org_tree.heading("size", text="Boyut")

        self._org_tree.column("category", width=150, minwidth=100)
        self._org_tree.column("filename", width=250, minwidth=150)
        self._org_tree.column("confidence", width=100, minwidth=70, anchor="center")
        self._org_tree.column("ext", width=55, minwidth=35, anchor="center")
        self._org_tree.column("size", width=75, minwidth=45, anchor="e")

        # Guvenilirlik renk tag'leri — foreground + background gerekli
        self._update_org_confidence_tags()

        org_scroll = ctk.CTkScrollbar(self._org_preview_frame, command=self._org_tree.yview)
        self._org_tree.configure(yscrollcommand=org_scroll.set)
        self._org_tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        org_scroll.grid(row=0, column=1, sticky="ns", pady=2)

        # İlerleme çubuğu
        self._org_progress_bar = ctk.CTkProgressBar(
            bottom, fg_color=T["surface2"],
            progress_color=T["gold"], corner_radius=3, height=4
        )
        self._org_progress_bar.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._org_progress_bar.set(0)

    def _update_org_confidence_tags(self):
        """Organizer treeview guvenilirlik tag renklerini ayarlar."""
        T = self.T
        bg = T["surface"]
        self._org_tree.tag_configure("conf_high",
            foreground="#22c55e", background=bg)      # Parlak yesil
        self._org_tree.tag_configure("conf_medium",
            foreground="#f59e0b", background=bg)      # Parlak turuncu
        self._org_tree.tag_configure("conf_unmatched",
            foreground=T["text_muted"], background=bg)  # Gri

    # Organizer: Kural Yönetimi

    def _org_add_rule(self, folder_name="", keywords=""):
        """Yeni bir kural satırı ekler."""
        T = self.T

        # Boş etiketi kaldır
        if self._org_empty_label.winfo_exists():
            self._org_empty_label.grid_forget()

        row_idx = len(self._org_rule_widgets)
        rule_frame = ctk.CTkFrame(
            self._org_rules_scrollable, fg_color=T["surface2"],
            corner_radius=6, border_width=1, border_color=T["border"]
        )
        rule_frame.grid(row=row_idx, column=0, sticky="ew", pady=(0, 4), padx=2)
        rule_frame.grid_columnconfigure(2, weight=1)

        # Kural numarası
        num_label = ctk.CTkLabel(
            rule_frame, text=f"#{row_idx + 1}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T["gold"], width=30
        )
        num_label.grid(row=0, column=0, padx=(10, 4), pady=8)

        # Klasör adı
        folder_label = ctk.CTkLabel(
            rule_frame, text="Klasor:",
            font=ctk.CTkFont(size=11),
            text_color=T["text_muted"], width=50
        )
        folder_label.grid(row=0, column=1, padx=(4, 2), pady=8)

        folder_var = ctk.StringVar(value=folder_name)
        folder_entry = ctk.CTkEntry(
            rule_frame, textvariable=folder_var,
            font=ctk.CTkFont(size=12),
            fg_color=T["surface"], border_width=1,
            border_color=T["border"],
            text_color=T["text_primary"],
            placeholder_text="Ornek: Burslu Ogrenciler",
            placeholder_text_color=T["text_muted"],
            width=180, height=30
        )
        folder_entry.grid(row=0, column=2, sticky="w", padx=(2, 8), pady=8)

        # Anahtar kelimeler
        kw_label = ctk.CTkLabel(
            rule_frame, text="Kelimeler:",
            font=ctk.CTkFont(size=11),
            text_color=T["text_muted"], width=70
        )
        kw_label.grid(row=0, column=3, padx=(8, 2), pady=8)

        kw_var = ctk.StringVar(value=keywords)
        kw_entry = ctk.CTkEntry(
            rule_frame, textvariable=kw_var,
            font=ctk.CTkFont(size=12),
            fg_color=T["surface"], border_width=1,
            border_color=T["border"],
            text_color=T["text_primary"],
            placeholder_text="burs, stipendium, scholarship (virgülle ayırın)",
            placeholder_text_color=T["text_muted"],
            height=30
        )
        kw_entry.grid(row=0, column=4, sticky="ew", padx=(2, 8), pady=8)
        rule_frame.grid_columnconfigure(4, weight=1)

        # Sil butonu
        del_btn = ctk.CTkButton(
            rule_frame, text="✕",
            font=ctk.CTkFont(size=14),
            fg_color="transparent", hover_color=T["hover"],
            text_color=T["error"], corner_radius=4,
            width=32, height=30,
            command=lambda: self._org_remove_rule(rule_frame)
        )
        del_btn.grid(row=0, column=5, padx=(0, 8), pady=8)

        widget_info = {
            "frame": rule_frame,
            "folder_var": folder_var,
            "folder_entry": folder_entry,
            "keywords_var": kw_var,
            "keywords_entry": kw_entry,
            "num_label": num_label,
            "folder_label": folder_label,
            "kw_label": kw_label,
            "del_btn": del_btn,
        }
        self._org_rule_widgets.append(widget_info)

    def _org_remove_rule(self, frame):
        """Belirli bir kuralı siler."""
        self._org_rule_widgets = [w for w in self._org_rule_widgets if w["frame"] != frame]
        frame.destroy()
        self._org_renumber_rules()

        # Hepsi silindiyse boş etiket göster
        if not self._org_rule_widgets:
            self._org_empty_label.grid(row=0, column=0, pady=40)

    def _org_renumber_rules(self):
        """Kural numaralarını yeniden sıralar."""
        for i, w in enumerate(self._org_rule_widgets):
            w["frame"].grid(row=i, column=0, sticky="ew", pady=(0, 4), padx=2)

    def _org_clear_rules(self):
        """Tüm kuralları temizler."""
        for w in self._org_rule_widgets:
            w["frame"].destroy()
        self._org_rule_widgets.clear()
        self._org_empty_label.grid(row=0, column=0, pady=40)

    def _org_load_template(self):
        """Hazır şablonu yükler."""
        self._org_clear_rules()
        template = ORGANIZER_TEMPLATES.get("Egitim Ataseligi", [])
        for rule_data in template:
            self._org_add_rule(
                folder_name=rule_data["folder_name"],
                keywords=rule_data["keywords"]
            )
        self._org_status_label.configure(
            text="Egitim Ataseligi sablonu yuklendi",
            text_color=self.T["success"]
        )

    def _org_select_target(self):
        """Hedef klasör seçiciyi açar."""
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Duzenlenmis dosyalar icin hedef klasor secin")
        if folder:
            self._org_target_dir.set(folder)

    def _org_get_rules(self) -> list:
        """Mevcut UI kurallarını OrganizerRule listesine çevirir."""
        rules = []
        for w in self._org_rule_widgets:
            folder = w["folder_var"].get().strip()
            keywords = w["keywords_var"].get().strip()
            if folder and keywords:
                rules.append(OrganizerRule.from_dict({
                    "folder_name": folder,
                    "keywords": keywords
                }))
        return rules

    # Organizer: Önizleme

    def _org_run_preview(self):
        """Dosyalari arka thread'de tarayip onizleme treeview'ina yukler."""
        rules = self._org_get_rules()
        if not rules:
            self._org_status_label.configure(
                text="Lutfen en az bir kural ekleyin",
                text_color=self.T["error"]
            )
            return

        self._org_tree.delete(*self._org_tree.get_children())
        self._org_btn_preview.configure(state="disabled", text="Taraniyor...")
        self._org_status_label.configure(
            text="Taraniyor...", text_color=self.T["text_muted"])
        self.update_idletasks()

        include_unmatched = self._org_include_unmatched.get()

        def _do_preview():
            preview = self.organizer.preview(rules, include_unmatched)
            self.ui_queue.put(("org_preview_done", preview))

        threading.Thread(target=_do_preview, daemon=True).start()

    def _org_apply_preview(self, preview):
        """Onizleme sonuclarini UI'a uygular (main thread'de calisir)."""
        self._org_tree.delete(*self._org_tree.get_children())

        for category, files in preview["categories"].items():
            for f in files:
                size_str = format_size(f["size"]) if f["size"] else "-"
                confidence = f.get("confidence", "low")
                conf_label = self.organizer.get_confidence_label(f["score"])

                tag = "conf_high" if confidence == "high" else "conf_medium"
                self._org_tree.insert("", "end", values=(
                    category, f["filename"], conf_label, f["ext"], size_str
                ), tags=(tag,))

        if self._org_include_unmatched.get() and preview["unmatched"]:
            for f in preview["unmatched"]:
                size_str = format_size(f["size"]) if f["size"] else "-"
                self._org_tree.insert("", "end", values=(
                    "Diger", f["filename"], "-", f["ext"], size_str
                ), tags=("conf_unmatched",))

        total = preview["total_matched"]
        unmatched = preview["total_unmatched"]

        status_text = f"{total} dosya eslesti (min skor: {MIN_SCORE_THRESHOLD})"
        if unmatched > 0:
            status_text += f" | {unmatched} eslesmeyen"

        self._org_status_label.configure(
            text=status_text,
            text_color=self.T["gold"] if total > 0 else self.T["error"]
        )

        self._org_btn_preview.configure(
            state="normal", text="Dosyalari Tara ve Onizle")

        if total > 0 or (self._org_include_unmatched.get() and unmatched > 0):
            copy_count = total + (unmatched if self._org_include_unmatched.get() else 0)
            self._org_btn_execute.configure(
                text=f"Duzenlemeyi Baslat ({copy_count} dosya)",
                state="normal"
            )
        else:
            self._org_btn_execute.configure(state="disabled")

    # Organizer: Kopyalama

    def _org_run_execute(self):
        """Onay aldıktan sonra kopyalama işlemini başlatır."""
        target = self._org_target_dir.get().strip()
        if not target:
            messagebox.showwarning(
                "Hedef Klasor Secilmedi",
                "Lütfen düzenlenmiş dosyaların kopyalanacağı\nbir hedef klasör seçin."
            )
            return

        rules = self._org_get_rules()
        if not rules:
            return

        # Önizleme bilgisi
        preview = self.organizer.preview(rules, self._org_include_unmatched.get())
        total = preview["total_matched"]
        if self._org_include_unmatched.get():
            total += preview["total_unmatched"]

        # Kategorilerin özeti
        summary_parts = []
        for cat, files in preview["categories"].items():
            if files:
                summary_parts.append(f"  • {cat}: {len(files)} dosya")
        if self._org_include_unmatched.get() and preview["unmatched"]:
            summary_parts.append(f"  • Diger: {len(preview['unmatched'])} dosya")
        summary_text = "\n".join(summary_parts)

        # Onay dialogu
        confirm = messagebox.askyesno(
            "Duzenleme Onayi",
            f"Toplam {total} dosya asagidaki kategorilere kopyalanacak:\n\n"
            f"{summary_text}\n\n"
            f"Hedef: {target}\n\n"
            f"⚠️ Orijinal dosyalar yerinde kalir, sadece KOPYALAMA yapilir.\n\n"
            f"Devam edilsin mi?"
        )

        if not confirm:
            return

        # Kopyalama başlat
        self._org_btn_execute.configure(text="Kopyalaniyor...", state="disabled")
        self._org_btn_preview.configure(state="disabled")
        self._org_progress_bar.set(0)

        self.organizer.execute(
            rules, target, self._org_include_unmatched.get()
        )

    # ABOUT TAB

    def _build_about_tab(self, parent):
        T = self.T
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Top: Logo + Brand
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, pady=(16, 0))

        logo = self._load_logo(120)
        if logo:
            ctk.CTkLabel(top, text="", image=logo).pack(pady=(0, 8))

        about_title = ctk.CTkLabel(
            top, text="VASTARION SCANNER",
            font=ctk.CTkFont(family="Georgia", size=20, weight="bold"),
            text_color=T["gold"]
        )
        about_title.pack(pady=(0, 2))
        self._themable_add(about_title, "label_gold")

        about_subtitle = ctk.CTkLabel(
            top, text=f"File Intelligence Engine  —  v{APP_VERSION}",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=T["text_muted"]
        )
        about_subtitle.pack(pady=(0, 6))
        self._themable_add(about_subtitle, "label_muted")

        about_line = tk.Canvas(top, width=60, height=1, bg=T["gold_dim"],
                  highlightthickness=0)
        about_line.pack(pady=(0, 10))
        self._themable_add(about_line, "canvas_gold_dim")

        # Bottom: Guide + Stats
        self.info_text = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=T["surface"], text_color=T["text_secondary"],
            corner_radius=8, border_width=1, border_color=T["border"],
            wrap="word"
        )
        self.info_text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.info_text.configure(state="disabled")

        btn_refresh_stats = ctk.CTkButton(
            parent, text="Istatistikleri Yenile",
            font=ctk.CTkFont(size=12),
            fg_color=T["surface2"], hover_color=T["hover"],
            text_color=T["text_secondary"], corner_radius=6,
            width=160, height=32, command=self._update_stats
        )
        btn_refresh_stats.grid(row=2, column=0, pady=(8, 4))
        self._themable_add(btn_refresh_stats, "ghost_btn")

    # STATUS BAR

    def _build_status_bar(self):
        T = self.T
        self._status_frame = ctk.CTkFrame(
            self, fg_color=T["surface"], corner_radius=0, height=34
        )
        self._status_frame.grid(row=3, column=0, sticky="ew")
        self._status_frame.grid_propagate(False)
        self._status_frame.grid_columnconfigure(1, weight=1)

        # Left: logo + status text
        left = ctk.CTkFrame(self._status_frame, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=(24, 0), pady=4)

        logo_s = self._load_logo(18)
        if logo_s:
            ctk.CTkLabel(left, text="", image=logo_s).pack(side="left", padx=(0, 8))

        self.lbl_status = ctk.CTkLabel(
            left, text="Hazir",
            font=ctk.CTkFont(size=11), text_color=T["text_muted"], anchor="w"
        )
        self.lbl_status.pack(side="left")

        # Right: watcher (watchdog modu mu, polling mi?)
        try:
            from core.watcher import _HAS_WATCHDOG
            wmode = "anlik" if _HAS_WATCHDOG else "30s"
        except Exception:
            wmode = "30s"
        self.lbl_watcher = ctk.CTkLabel(
            self._status_frame, text=f"● Watcher aktif ({wmode})",
            font=ctk.CTkFont(size=11),
            text_color=T["success"], anchor="e"
        )
        self.lbl_watcher.grid(row=0, column=2, sticky="e", padx=(0, 24), pady=4)

    # SEARCH

    def _on_search_typed(self, *args):
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._execute_search)

    def _execute_search(self):
        T = self.T
        query = self.search_var.get().strip()
        self.tree.delete(*self.tree.get_children())
        self._result_paths.clear()
        self._all_results.clear()
        self._loaded_count = 0
        self._hover_item = None

        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.configure(state="disabled")

        if not query or len(query) < 2:
            self.lbl_result_count.configure(
                text="En az 2 karakter girin", text_color=T["text_muted"])
            self.lbl_search_time.configure(text="")
            self._safe(self.btn_export_csv, state="disabled")
            return

        # Arama gecmisine ekle
        self._add_to_history(query)

        result = self.search_engine.search(query, limit=500)
        self.lbl_search_time.configure(text=f"{result['elapsed_ms']} ms")

        if result["count"] == 0:
            self.lbl_result_count.configure(
                text=f'"{query}" icin sonuc bulunamadi', text_color=T["error"])
            self._safe(self.btn_export_csv, state="disabled")
            return

        self._all_results = result["results"]
        self.lbl_result_count.configure(
            text=f'"{query}" icin {result["count"]} sonuc', text_color=T["gold"])

        # Export butonu artik aktif
        self._safe(self.btn_export_csv, state="normal")

        # Lazy loading: sadece ilk 50'yi yukle
        self._load_next_batch()

    def _load_next_batch(self):
        """Sonuclarin sonraki batch'ini Treeview'a yukler."""
        end = min(self._loaded_count + self._LAZY_BATCH, len(self._all_results))
        for r in self._all_results[self._loaded_count:end]:
            size_str = format_size(r["size"]) if r["size"] else "-"
            snippet = r.get("snippet", "")[:80] or "(dosya adinda eslesme)"
            self.tree.insert("", "end", values=(
                r["filename"], snippet, r["directory"], r["ext"], size_str
            ), tags=("normal",))
            self._result_paths.append(r["filepath"])
        self._loaded_count = end

    def _tree_scroll_handler(self, *args):
        """Scrollbar'a veri gonderir + lazy loading tetikler."""
        self._tree_scrollbar.set(*args)
        self._on_tree_scroll(*args)

    def _on_tree_scroll(self, *args):
        """Treeview scroll edildiginde daha fazla sonuc yukler."""
        # Yscrollbar'dan gelen deger 0.0 - 1.0 arasi
        if self._loaded_count < len(self._all_results):
            # Scroll sonuna yaklastiginda yukle
            try:
                bottom = float(args[1]) if len(args) > 1 else 0
                if bottom > 0.85:
                    self._load_next_batch()
            except (ValueError, IndexError):
                pass

    def _add_to_history(self, query: str):
        """Arama gecmisine ekler (max 20)."""
        q = query.strip()
        if not q:
            return
        if q in self._search_history:
            self._search_history.remove(q)
        self._search_history.insert(0, q)
        if len(self._search_history) > 20:
            self._search_history.pop()

    def _show_search_history(self):
        """Arama gecmisini dropdown olarak gosterir."""
        if not self._search_history:
            return

        T = self.T
        menu = tk.Menu(
            self, tearoff=0,
            bg=T["surface2"], fg=T["text_primary"],
            activebackground=T["hover"], activeforeground=T["gold"],
            font=("Segoe UI", 10), relief="flat", bd=1
        )
        for q in self._search_history[:15]:
            display = q if len(q) <= 40 else q[:37] + "..."
            menu.add_command(label=f"  {display}",
                command=lambda query=q: self._apply_history(query))

        if len(self._search_history) > 0:
            menu.add_separator()
            menu.add_command(label="  Gecmisi Temizle",
                command=self._clear_history)

        # Butonun altinda goster
        try:
            x = self._btn_history.winfo_rootx()
            y = self._btn_history.winfo_rooty() + self._btn_history.winfo_height()
            menu.post(x, y)
        except Exception:
            pass

    def _apply_history(self, query: str):
        """Gecmisten secilen aramayi uygular."""
        self.search_var.set(query)
        self.entry_search.focus_set()

    def _clear_history(self):
        """Arama gecmisini temizler."""
        self._search_history.clear()

    # EXPORT

    def _export_results_csv(self):
        """Mevcut arama sonuclarini UTF-8 CSV olarak kaydet.

        UTF-8 BOM ile yazilir ki Excel'de Turkce karakterler bozulmasin.
        Snippet'lar tek satira indirgenir, virgul ve tirnak escape edilir.
        """
        if not self._all_results:
            return

        from tkinter import filedialog
        import csv

        query = self.search_var.get().strip()
        default_name = f"vastarion_{query[:30] or 'sonuclar'}.csv"
        # Dosya adindaki yasak karakterleri temizle
        for ch in '<>:"/\\|?*':
            default_name = default_name.replace(ch, "_")

        filepath = filedialog.asksaveasfilename(
            title="CSV olarak kaydet",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV (Excel uyumlu)", "*.csv"), ("Tum dosyalar", "*.*")]
        )
        if not filepath:
            return

        try:
            # utf-8-sig → Excel'in UTF-8 BOM ile dogru acmasi icin
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                writer.writerow([
                    "Dosya Adi", "Eslesme", "Klasor", "Tur", "Boyut (byte)",
                    "Degisiklik Tarihi", "Tam Yol"
                ])
                for r in self._all_results:
                    snippet = (r.get("snippet") or "").replace("\n", " ").strip()
                    writer.writerow([
                        r.get("filename", ""),
                        snippet,
                        r.get("directory", ""),
                        r.get("ext", ""),
                        r.get("size", "") or "",
                        r.get("modified", "") or "",
                        r.get("filepath", ""),
                    ])

            count = len(self._all_results)
            self.lbl_status.configure(
                text=f"CSV kaydedildi: {count} satir → {os.path.basename(filepath)}")

            # Klasoru acmayi teklif et
            open_it = messagebox.askyesno(
                "CSV Kaydedildi",
                f"{count} sonuc basariyla kaydedildi:\n{filepath}\n\n"
                f"Dosyanin bulundugu klasoru acmak ister misiniz?"
            )
            if open_it:
                folder = os.path.dirname(filepath)
                if sys.platform == "win32":
                    os.startfile(folder)
                else:
                    os.system(f'xdg-open "{folder}"')
        except Exception as e:
            log.error(f"CSV export hatasi: {e}")
            messagebox.showerror(
                "CSV Kaydedilemedi",
                f"Dosya yazilirken hata olustu:\n\n{e}"
            )

    def _on_tree_select(self, event=None):
        T = self.T
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.insert("end", "  Yukleniyor...")
        self.txt_preview.configure(state="disabled")

        sel = self.tree.selection()
        if not sel:
            self.txt_preview.configure(state="normal")
            self.txt_preview.delete("1.0", "end")
            self.txt_preview.configure(state="disabled")
            return

        idx = self.tree.index(sel[0])
        if idx >= len(self._result_paths):
            self.txt_preview.configure(state="disabled")
            return

        filepath = self._result_paths[idx]
        query = self.search_var.get().strip()
        if not query:
            self.txt_preview.configure(state="normal")
            self.txt_preview.delete("1.0", "end")
            self.txt_preview.configure(state="disabled")
            return

        # Cache'de varsa hemen goster, yoksa thread ile yukle
        if filepath in self._content_cache:
            self._render_preview(filepath, query)
        else:
            threading.Thread(
                target=self._load_preview_async,
                args=(filepath, query), daemon=True
            ).start()

    def _load_preview_async(self, filepath, query):
        """Dosya icerigini arka planda okur, sonra UI'a gonderir."""
        content = extract_content(filepath) if os.path.exists(filepath) else ""
        self._content_cache[filepath] = content
        if len(self._content_cache) > 150:
            # En eski 50 tanesini sil
            keys = list(self._content_cache.keys())
            for k in keys[:50]:
                del self._content_cache[k]
        # UI thread'inde render et
        self.after(0, lambda: self._render_preview(filepath, query))

    def _render_preview(self, filepath, query):
        """Onizleme panelini doldurur (UI thread'inde calisir)."""
        T = self.T
        content = self._content_cache.get(filepath, "")
        query_lower = tr_lower(query)

        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")

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
            if idx > pos:
                self.txt_preview.insert("end", text[pos:idx])
            self.txt_preview.insert("end", text[idx:idx+len(query)], "highlight")
            pos = idx + len(query)

    # HOVER

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
                    self._folder_hover_idx, bg=self.T["surface"], fg=self.T["text_primary"])
            except tk.TclError:
                pass
        self._folder_hover_idx = idx
        if 0 <= idx < self.folder_listbox.size():
            self.folder_listbox.itemconfig(idx, bg=self.T["hover"], fg=self.T["gold_light"])

    def _on_folder_leave(self, event):
        if self._folder_hover_idx is not None:
            try:
                self.folder_listbox.itemconfig(
                    self._folder_hover_idx, bg=self.T["surface"], fg=self.T["text_primary"])
            except tk.TclError:
                pass
            self._folder_hover_idx = None

    # FILE OPERATIONS

    def _get_selected_path(self):
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        return self._result_paths[idx] if idx < len(self._result_paths) else None

    def _open_file(self, event=None):
        path = self._get_selected_path()
        if path and os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            else:
                os.system(f'xdg-open "{path}"')

    def _open_folder(self):
        path = self._get_selected_path()
        if path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                if sys.platform == "win32":
                    os.startfile(folder)
                else:
                    os.system(f'xdg-open "{folder}"')

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

    # FOLDER MANAGEMENT

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

    # QUEUE

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
                # Organizer mesajlari
                elif msg_type == "org_preview_done":
                    self._org_apply_preview(data)
                elif msg_type == "org_status":
                    self._org_status_label.configure(text=data)
                elif msg_type == "org_progress":
                    copied, total, errors = data
                    self._org_progress_bar.set(copied / max(total, 1))
                    self._org_status_label.configure(
                        text=f"Kopyalaniyor: {copied}/{total}" +
                             (f" ({errors} hata)" if errors else ""))
                elif msg_type == "org_done":
                    copied, total, errors = data
                    self._org_progress_bar.set(1 if copied > 0 else 0)
                    self._org_btn_execute.configure(
                        text="✅ Duzenlemeyi Baslat", state="disabled")
                    self._org_btn_preview.configure(state="normal")
                    if copied > 0:
                        self._org_status_label.configure(
                            text=f"Tamamlandi: {copied} dosya kopyalandi" +
                                 (f", {errors} hata" if errors else ""),
                            text_color=self.T["success"]
                        )
                        target = self._org_target_dir.get().strip()
                        if target and os.path.exists(target):
                            open_it = messagebox.askyesno(
                                "Duzenleme Tamamlandi",
                                f"{copied} dosya basariyla kopyalandi!\n\n"
                                f"Hedef klasoru acmak ister misiniz?\n{target}"
                            )
                            if open_it:
                                if sys.platform == "win32":
                                    os.startfile(target)
                                else:
                                    os.system(f'xdg-open "{target}"')
        except queue.Empty:
            pass
        self.after(150, self._process_queue)

    # STATS

    def _update_stats(self):
        stats = self.db.get_stats()
        total = stats["total"]
        dirs_count = len(self.db.get_watched_dirs())

        self.lbl_stats.configure(text=f"{total:,} dosya indekslendi")

        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")

        ins = self.info_text.insert
        sep = "-" * 50

        ins("end", "\n")
        ins("end", "   NASIL KULLANILIR?\n")
        ins("end", "   " + sep + "\n\n")
        ins("end", "   1. KLASORLER sekmesinden taranacak klasorleri ekleyin\n")
        ins("end", "   2. Taramayi Baslat butonuna basin\n")
        ins("end", "   3. Yukardaki arama kutusuna yazip dosya arayin\n")
        ins("end", "   4. DUZENLE sekmesinden dosyalari otomatik kategorize edin\n")
        ins("end", "   5. Sonuclari CSV olarak Excel'e disa aktarabilirsiniz\n\n")

        ins("end", "   DESTEKLENEN DOSYA TURLERI\n")
        ins("end", "   " + sep + "\n\n")
        ins("end", "   .pdf  .docx  .xlsx  .txt  .csv  .md\n")
        ins("end", "   .py   .js    .html  .css  .json\n\n")

        ins("end", "   OZELLIKLER\n")
        ins("end", "   " + sep + "\n\n")
        ins("end", "   - Turkce karakter destegi\n")
        ins("end", "   - Anlik veya 30sn dosya izleyici\n")
        ins("end", "   - Akilli esleme + guvenilirlik renkleri\n")
        ins("end", "   - Orijinal dosyalar yerinde kalir (sadece kopyalama)\n")
        ins("end", "   - CSV disa aktarma\n\n")

        ins("end", "   ISTATISTIKLER\n")
        ins("end", "   " + sep + "\n\n")
        ins("end", f"   Toplam Dosya          {total:,}\n")
        ins("end", f"   Izlenen Klasor        {dirs_count}\n")
        try:
            from core.watcher import _HAS_WATCHDOG
            wmode = "Aktif (anlik)" if _HAS_WATCHDOG else "Aktif (30s)"
        except Exception:
            wmode = "Aktif"
        ins("end", f"   Watcher               {wmode}\n")
        ins("end", f"   Veritabani            {self.db.db_path}\n")

        if stats["by_extension"]:
            ins("end", "\n\n   DOSYA DAGILIMI\n")
            ins("end", "   " + sep + "\n\n")
            max_c = max(stats["by_extension"].values(), default=1)
            for ext, count in sorted(stats["by_extension"].items(), key=lambda x: -x[1]):
                bar_len = int(count / max(max_c, 1) * 20)
                bar = "#" * bar_len + "." * (20 - bar_len)
                pct = count / max(total, 1) * 100
                ins("end", f"   {ext:8s}  {bar}  {count:>5,}  ({pct:.1f}%)\n")

        ins("end", "\n\n   " + sep + "\n")
        ins("end", f"   Vastarion Scanner v{APP_VERSION}\n")
        ins("end", "   github.com/callmeouz/vastarion-scanner\n")

        self.info_text.configure(state="disabled")

    def _on_close(self):
        log.info("Uygulama kapatiliyor")
        self.worker.stop()
        self.organizer.stop()
        self.watcher.stop()
        self.db.close()
        self.destroy()
