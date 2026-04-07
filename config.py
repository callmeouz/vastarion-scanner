import os
from pathlib import Path

# Uygulama Bilgileri
APP_NAME = "Vastarion Scanner"
APP_VERSION = "1.0.0"

# Dizin Ayarlari
USER_HOME = Path.home()
APP_DIR = USER_HOME / ".vastarion"
DB_PATH = APP_DIR / "index.db"
LOG_PATH = APP_DIR / "vastarion.log"

# ═══════════════════════════════════════════════
# DESIGN SYSTEM — Premium Dark
# ═══════════════════════════════════════════════
THEME = {
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
}

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

os.makedirs(APP_DIR, exist_ok=True)
