import time
import os
import threading
from datetime import datetime
from core.scanner import scan_directory
from core.parsers import extract_content
from utils.file_utils import get_file_hash
from utils.text_utils import normalize_turkish
from logger import log


class FileWatcher:
    """Arka planda dosya degisikliklerini izleyen sinif."""

    def __init__(self, db, interval=30):
        self.db = db
        self.interval = interval
        self._thread = None
        self._running = False
        self._callback = None

    def on_change(self, callback):
        """Degisiklik alglandiginda cagrilacak fonksiyon."""
        self._callback = callback

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info(f"Watcher basladi. {self.interval} saniyede bir kontrol edilecek.")

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(self.interval)
            if not self._running:
                break
            try:
                changes = self._check()
                if changes > 0 and self._callback:
                    self._callback(changes)
            except Exception as e:
                log.error(f"Watcher hatasi: {e}")

    def _check(self) -> int:
        dirs = self.db.get_watched_dirs()
        if not dirs:
            return 0

        indexed = self.db.get_all_indexed_paths()
        current = set()
        changes = 0

        for folder in dirs:
            for filepath, ext in scan_directory(folder):
                current.add(filepath)
                try:
                    stat = os.stat(filepath)
                    mtime_iso = datetime.fromtimestamp(stat.st_mtime).isoformat()
                    existing = self.db.get_file_mtime(filepath)

                    if existing is None or existing != mtime_iso:
                        name = os.path.basename(filepath)
                        directory = os.path.dirname(filepath)
                        content = extract_content(filepath)
                        normalized = normalize_turkish(content)
                        file_hash = get_file_hash(filepath)

                        self.db.upsert_file(
                            filepath, name, ext, directory,
                            content, normalized, file_hash, mtime_iso, stat.st_size
                        )
                        changes += 1
                        log.info(f"Watcher: Guncellendi — {filepath}")
                except Exception as e:
                    log.error(f"Watcher dosya hatasi ({filepath}): {e}")

        # Silinen dosyalar
        deleted = indexed - current
        for path in deleted:
            self.db.delete_file(path)
            changes += 1
            log.info(f"Watcher: Silindi — {path}")

        if changes:
            self.db.commit()
            log.info(f"Watcher: {changes} degisiklik islendi.")

        return changes
