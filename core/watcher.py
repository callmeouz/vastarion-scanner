import time
import os
import threading
from datetime import datetime
from core.scanner import scan_directory
from core.parsers import extract_content
from utils.file_utils import get_file_hash
from utils.text_utils import normalize_turkish
from config import SUPPORTED_EXTENSIONS
from logger import log

# Opsiyonel: watchdog kurulu ise event-driven izleme kullanilir.
# Yoksa eski 30s polling fallback'i devreye girer.
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _HAS_WATCHDOG = True
except ImportError:
    Observer = None
    FileSystemEventHandler = object
    _HAS_WATCHDOG = False


class FileWatcher:
    """Arka planda dosya degisikliklerini izleyen sinif.

    Iki mod:
    - watchdog kurulu ise: event-driven (anlik tepki, dusuk CPU)
    - degilse: 30s polling (geriye uyumlu fallback)
    """

    def __init__(self, db, interval=30):
        self.db = db
        self.interval = interval
        self._thread = None
        self._running = False
        self._callback = None
        # Watchdog state
        self._observer = None
        self._debounce_timer = None
        self._pending_changes = 0
        self._lock = threading.Lock()

    def on_change(self, callback):
        """Degisiklik alglandiginda cagrilacak fonksiyon."""
        self._callback = callback

    def start(self):
        self._running = True
        if _HAS_WATCHDOG:
            self._start_watchdog()
        else:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            log.info(f"Watcher basladi (polling). {self.interval}s aralikla kontrol.")

    def stop(self):
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception as e:
                log.warning(f"Watchdog observer durdurulurken hata: {e}")
            self._observer = None

    # ── Watchdog (event-driven) ─────────────────────────

    def _start_watchdog(self):
        """watchdog Observer'i tum izlenen klasorlere bagla."""
        try:
            handler = _ChangeHandler(self._on_fs_event)
            observer = Observer()
            dirs = self.db.get_watched_dirs()
            attached = 0
            for d in dirs:
                if os.path.isdir(d):
                    try:
                        observer.schedule(handler, d, recursive=True)
                        attached += 1
                    except Exception as e:
                        log.warning(f"Watchdog '{d}' baglanamadi: {e}")
            observer.start()
            self._observer = observer
            log.info(f"Watcher basladi (watchdog). {attached} klasor izleniyor.")
        except Exception as e:
            log.error(f"Watchdog baslamadi, polling'e dusulduyor: {e}")
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _on_fs_event(self, event_path: str):
        """watchdog event'i geldiginde cagrilir — debounce ile toplu islem."""
        if not self._running:
            return
        # Sadece desteklenen uzantilar
        ext = os.path.splitext(event_path)[1].lower()
        if ext and ext not in SUPPORTED_EXTENSIONS:
            return

        with self._lock:
            self._pending_changes += 1
            # 2 saniye debounce: art arda gelen event'leri tek tarama olarak isle
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(2.0, self._flush_pending)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _flush_pending(self):
        """Debounce suresi sonunda birikenleri tek seferde tarayip rapor et."""
        with self._lock:
            self._pending_changes = 0
            self._debounce_timer = None
        try:
            changes = self._check()
            if changes > 0 and self._callback:
                self._callback(changes)
        except Exception as e:
            log.error(f"Watchdog flush hatasi: {e}")

    # ── Polling (fallback) ──────────────────────────────

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


# ──────────────────────────────────────────────────────────
# Watchdog event handler — sadece watchdog kurulu ise kullanilir
# ──────────────────────────────────────────────────────────

class _ChangeHandler(FileSystemEventHandler):
    """Watchdog'tan gelen tum dosya event'lerini tek bir callback'e yonlendirir."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def on_created(self, event):
        if not event.is_directory:
            self._callback(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._callback(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._callback(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._callback(event.dest_path or event.src_path)
