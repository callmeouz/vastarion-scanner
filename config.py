import os
import json
from pathlib import Path

# Uygulama Bilgileri
APP_NAME = "Vastarion Scanner"
APP_VERSION = "1.2.0"

# Dizin Ayarlari
USER_HOME = Path.home()
APP_DIR = USER_HOME / ".vastarion"
DB_PATH = APP_DIR / "index.db"
LOG_PATH = APP_DIR / "vastarion.log"
SETTINGS_PATH = APP_DIR / "settings.json"

# ═══════════════════════════════════════════════
# DESIGN SYSTEM — Dual Theme
# ═══════════════════════════════════════════════

THEME_DARK = {
    # Backgrounds (derinlik katmanlari)
    "bg":           "#0B0B0C",   # En derin — ana arka plan
    "surface":      "#121214",   # Kartlar, paneller
    "surface2":     "#1A1A1D",   # Ustune cikan elementler
    "hover":        "#202024",   # Hover durumu

    # Borders
    "border":       "#2A2A2E",   # Standart kenar
    "border_subtle":"#1E1E22",   # Ince, hafif kenar

    # Accent (Gold)
    "gold":         "#C6A96B",   # Primary accent
    "gold_light":   "#D4BC85",   # Gold hover / active
    "gold_dim":     "#8A7A50",   # Gold muted

    # Text
    "text_primary": "#EAEAEA",   # Ana metin
    "text_secondary":"#9A9AA0",  # Ikincil metin
    "text_muted":   "#6A6A70",   # Soluk metin

    # Semantic
    "success":      "#4ade80",
    "error":        "#f87171",
    "warning":      "#fbbf24",
}

THEME_LIGHT = {
    # Backgrounds
    "bg":           "#F5F5F0",
    "surface":      "#FFFFFF",
    "surface2":     "#F0EDE8",
    "hover":        "#E8E5E0",

    # Borders
    "border":       "#D4D0CC",
    "border_subtle":"#E0DDD8",

    # Accent (Gold — daha koyu, okunabilir)
    "gold":         "#8B6914",
    "gold_light":   "#A07A1A",
    "gold_dim":     "#C4A855",

    # Text (yuksek kontrast)
    "text_primary": "#1A1A1A",
    "text_secondary":"#555555",
    "text_muted":   "#888888",

    # Semantic
    "success":      "#16a34a",
    "error":        "#dc2626",
    "warning":      "#d97706",
}

# ═══════════════════════════════════════════════
# SETTINGS — Kalici tercihler
# ═══════════════════════════════════════════════

def load_settings() -> dict:
    """Kullanici tercihlerini JSON'dan yukler."""
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_settings(settings: dict):
    """Kullanici tercihlerini JSON'a yazar."""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_active_theme_mode() -> str:
    """Aktif tema modunu dondurur: 'dark' veya 'light'."""
    settings = load_settings()
    return settings.get("theme_mode", "dark")


def set_theme_mode(mode: str):
    """Tema modunu kaydeder."""
    settings = load_settings()
    settings["theme_mode"] = mode
    save_settings(settings)


def get_active_theme() -> dict:
    """Aktif temaya gore renk sozlugunu dondurur."""
    mode = get_active_theme_mode()
    return THEME_LIGHT if mode == "light" else THEME_DARK


# Geriye uyumluluk — mevcut kodun calismasi icin
THEME = get_active_theme()

# Otomatik Taranacak Klasorler
DEFAULT_SCAN_PATHS = [
    USER_HOME / "Documents",
    USER_HOME / "Desktop",
    USER_HOME / "Downloads",
]

_onedrive = USER_HOME / "OneDrive"
if _onedrive.exists():
    for _sub in ["Documents", "Desktop", "Downloads"]:
        _p = _onedrive / _sub
        if _p.exists():
            DEFAULT_SCAN_PATHS.append(_p)

# Tarama Ayarlari
SUPPORTED_EXTENSIONS = {
    ".txt", ".pdf", ".docx", ".xlsx", ".csv",
    ".py", ".js", ".html", ".css", ".json", ".md"
}

IGNORE_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    "Windows", "AppData", "Program Files", "Program Files (x86)",
    "ProgramData", "$Recycle.Bin", "System Volume Information",
    ".vastarion", ".cache", "Temp"
}

# Dosya Duzenleme Sablonlari — Egitim Ataseligi
ORGANIZER_TEMPLATES = {
    "Egitim Ataseligi": [
        {"folder_name": "Burslu Ogrenciler", "keywords": "burs, stipendium, scholarship, burslu, YLSY, YTB, burslandirma"},
        {"folder_name": "Ogretmenler", "keywords": "öğretmen, lehrer, teacher, maarif, okutman, ogretmen, ögretmen"},
        {"folder_name": "Askerlik", "keywords": "askerlik, tecil, sevk, terhis, celp, askerlik subesi, wehrdienst"},
        {"folder_name": "Gelecek Ogrenciler", "keywords": "başvuru, kabul, zulassung, admission, kayıt, basvuru, immatrikulation, ogrenci basvuru"},
        {"folder_name": "Vize ve Pasaport", "keywords": "vize, pasaport, visum, aufenthaltstitel, oturma izni, ikamet"},
        {"folder_name": "Resmi Yazilar", "keywords": "resmi yazi, yazışma, ust yazi, bakanlik, büyükelçilik, konsolosluk, ataselige"},
    ]
}

os.makedirs(APP_DIR, exist_ok=True)
