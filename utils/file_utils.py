import hashlib
import os
from datetime import datetime

def get_file_hash(filepath: str, chunk_size: int = 8192) -> str:
    """Dosyanin icerigine gore MD5 hash'ini hesaplar. Degisiklik tespiti icin kullanilir."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

def format_size(size_in_bytes: int) -> str:
    """Bayt cinsinden boyutu okunabilir formata (KB, MB) cevirir."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} TB"

def format_date(timestamp) -> str:
    """Timestamp degerini okunabilir tarih formatina cevirir."""
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError, OSError):
        return "-"
