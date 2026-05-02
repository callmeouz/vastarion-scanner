import os
import json
from pathlib import Path

APP_NAME = "Vastarion Scanner"
APP_VERSION = "1.2.0"

USER_HOME = Path.home()
APP_DIR = USER_HOME / ".vastarion"
DB_PATH = APP_DIR / "index.db"
LOG_PATH = APP_DIR / "vastarion.log"
SETTINGS_PATH = APP_DIR / "settings.json"

THEME_DARK = {
    "bg":           "#0B0B0C",
    "surface":      "#121214",
    "surface2":     "#1A1A1D",
    "hover":        "#202024",
    "border":       "#2A2A2E",
    "border_subtle":"#1E1E22",
    "gold":         "#C6A96B",
    "gold_light":   "#D4BC85",
    "gold_dim":     "#8A7A50",
    "text_primary": "#EAEAEA",
    "text_secondary":"#9A9AA0",
    "text_muted":   "#6A6A70",
    "success":      "#4ade80",
    "error":        "#f87171",
    "warning":      "#fbbf24",
}

THEME_LIGHT = {
    "bg":           "#F5F2EC",
    "surface":      "#FBF9F4",
    "surface2":     "#EFEAE0",
    "hover":        "#E5DFD2",
    "border":       "#C9C2B5",
    "border_subtle":"#DDD7CB",
    "gold":         "#8B6914",
    "gold_light":   "#6F5410",
    "gold_dim":     "#B89D5A",
    "text_primary": "#2A2A2A",
    "text_secondary":"#4A4A4A",
    "text_muted":   "#7A7468",
    "success":      "#15803d",
    "error":        "#b91c1c",
    "warning":      "#b45309",
}


def load_settings() -> dict:
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_settings(settings: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_active_theme_mode() -> str:
    settings = load_settings()
    return settings.get("theme_mode", "dark")


def set_theme_mode(mode: str):
    settings = load_settings()
    settings["theme_mode"] = mode
    save_settings(settings)


def get_active_theme() -> dict:
    mode = get_active_theme_mode()
    return THEME_LIGHT if mode == "light" else THEME_DARK


THEME = get_active_theme()

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

ORGANIZER_TEMPLATES = {
    "Egitim Ataseligi": [
        {"folder_name": "Burslu Ogrenciler", "keywords": "burs, stipendium, scholarship, burslu, YLSY, YTB, burslandirma"},
        {"folder_name": "Ogretmenler", "keywords": "ogretmen, lehrer, teacher, maarif, okutman"},
        {"folder_name": "Askerlik", "keywords": "askerlik, tecil, sevk, terhis, celp, askerlik subesi, wehrdienst"},
        {"folder_name": "Gelecek Ogrenciler", "keywords": "basvuru, kabul, zulassung, admission, kayit, immatrikulation, ogrenci basvuru"},
        {"folder_name": "Vize ve Pasaport", "keywords": "vize, pasaport, visum, aufenthaltstitel, oturma izni, ikamet"},
        {"folder_name": "Resmi Yazilar", "keywords": "resmi yazi, yazisma, ust yazi, bakanlik, buyukelcilik, konsolosluk, ataselige"},
    ]
}

os.makedirs(APP_DIR, exist_ok=True)
