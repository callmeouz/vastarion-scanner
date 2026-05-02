import os
from config import IGNORE_DIRS, SUPPORTED_EXTENSIONS
from logger import log

def scan_directory(base_path: str):
    """
    Belirtilen dizini recursive (alt klasorlerle) tarar.
    Desteklenen dosyalari yield ile dondurur (memory dostu).
    """
    if not os.path.exists(base_path):
        log.warning(f"Tarama dizini bulunamadi: {base_path}")
        return

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                filepath = os.path.join(root, file)
                yield filepath, ext
