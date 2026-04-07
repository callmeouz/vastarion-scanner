import threading
import os
from datetime import datetime
from core.scanner import scan_directory
from core.parsers import extract_content
from utils.file_utils import get_file_hash
from utils.text_utils import normalize_turkish
from logger import log


class IndexWorker:
    """Arka planda dosyalari tarayan ve indeksleyen isci sinif."""

    def __init__(self, db, ui_queue):
        self.db = db
        self.ui_queue = ui_queue
        self.is_running = False
        self._thread = None

    def start(self, dirs: list):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run, args=(list(dirs),), daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False

    def _run(self, dirs):
        try:
            for folder in dirs:
                if not self.is_running:
                    break
                self._index_folder(folder)
            self.ui_queue.put(("all_done", None))
        except Exception as e:
            log.error(f"Worker hata: {e}")
            self.ui_queue.put(("error", str(e)))
        finally:
            self.is_running = False

    def _index_folder(self, folder: str):
        self.ui_queue.put(("status", f"Taraniyor: {folder}"))

        files = list(scan_directory(folder))
        total = len(files)
        indexed = 0
        skipped = 0

        self.ui_queue.put(("total", total))

        for filepath, ext in files:
            if not self.is_running:
                break
            try:
                stat = os.stat(filepath)
                mtime_iso = datetime.fromtimestamp(stat.st_mtime).isoformat()

                existing = self.db.get_file_mtime(filepath)
                if existing and existing == mtime_iso:
                    skipped += 1
                    indexed += 1
                    if indexed % 100 == 0:
                        self.ui_queue.put(("progress", (indexed, total, skipped)))
                    continue

                content = extract_content(filepath)
                normalized = normalize_turkish(content)
                file_hash = get_file_hash(filepath)
                name = os.path.basename(filepath)
                directory = os.path.dirname(filepath)
                size = stat.st_size

                self.db.upsert_file(
                    filepath, name, ext, directory,
                    content, normalized, file_hash, mtime_iso, size
                )

                if indexed % 50 == 0:
                    self.db.commit()

            except Exception as e:
                log.error(f"Dosya islenirken hata ({filepath}): {e}")

            indexed += 1
            if indexed % 20 == 0:
                self.ui_queue.put(("progress", (indexed, total, skipped)))

        self.db.commit()
        self.ui_queue.put(("progress", (indexed, total, skipped)))
        self.ui_queue.put(("done", (indexed, total, skipped)))
