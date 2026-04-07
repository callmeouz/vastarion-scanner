import sqlite3
import os
from config import DB_PATH, DEFAULT_SCAN_PATHS
from logger import log


class Database:
    """SQLite + FTS5 veritabani yonetim sinifi."""

    def __init__(self):
        self.db_path = str(DB_PATH)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._setup_pragmas()
        self._create_tables()
        self._setup_defaults()

    def _setup_pragmas(self):
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")
        self.conn.execute("PRAGMA temp_store=MEMORY")

    def _create_tables(self):
        c = self.conn.cursor()

        # Ana dosya tablosu
        c.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                ext TEXT,
                directory TEXT,
                content TEXT,
                normalized_content TEXT,
                file_hash TEXT,
                mtime TEXT,
                size INTEGER
            )
        """)

        # FTS5 sanal tablosu (arama icin)
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                name, content, normalized_content,
                content='files', content_rowid='id',
                tokenize='unicode61 remove_diacritics 1'
            )
        """)

        # Otomatik senkronizasyon triggerlari
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
                INSERT INTO files_fts(rowid, name, content, normalized_content)
                VALUES (new.id, new.name, new.content, new.normalized_content);
            END
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, name, content, normalized_content)
                VALUES ('delete', old.id, old.name, old.content, old.normalized_content);
            END
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, name, content, normalized_content)
                VALUES ('delete', old.id, old.name, old.content, old.normalized_content);
                INSERT INTO files_fts(rowid, name, content, normalized_content)
                VALUES (new.id, new.name, new.content, new.normalized_content);
            END
        """)

        # Izlenen klasorler
        c.execute("""
            CREATE TABLE IF NOT EXISTS watched_dirs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL
            )
        """)

        self.conn.commit()
        log.info("Veritabani basariyla baslatildi.")

    def _setup_defaults(self):
        """Ilk calistirmada standart klasorleri ekler."""
        if not self.get_watched_dirs():
            for p in DEFAULT_SCAN_PATHS:
                if p.exists():
                    self.add_watched_dir(str(p))

    # -- Klasor yonetimi --

    def add_watched_dir(self, path: str):
        try:
            self.conn.execute("INSERT OR IGNORE INTO watched_dirs (path) VALUES (?)", (path,))
            self.conn.commit()
        except Exception as e:
            log.error(f"Klasor eklenirken hata: {e}")

    def remove_watched_dir(self, path: str):
        try:
            self.conn.execute("DELETE FROM watched_dirs WHERE path = ?", (path,))
            self.conn.commit()
        except Exception as e:
            log.error(f"Klasor silinirken hata: {e}")

    def get_watched_dirs(self) -> list:
        cursor = self.conn.execute("SELECT path FROM watched_dirs")
        return [row[0] for row in cursor.fetchall()]

    # -- Dosya islemleri --

    def upsert_file(self, path, name, ext, directory, content, normalized_content, file_hash, mtime, size):
        try:
            self.conn.execute("""
                INSERT INTO files (path, name, ext, directory, content, normalized_content, file_hash, mtime, size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name=excluded.name, ext=excluded.ext, directory=excluded.directory,
                    content=excluded.content, normalized_content=excluded.normalized_content,
                    file_hash=excluded.file_hash, mtime=excluded.mtime, size=excluded.size
            """, (path, name, ext, directory, content, normalized_content, file_hash, mtime, size))
        except Exception as e:
            log.error(f"Dosya kaydedilirken hata ({path}): {e}")

    def commit(self):
        self.conn.commit()

    def get_file_mtime(self, path: str):
        cursor = self.conn.execute("SELECT mtime FROM files WHERE path = ?", (path,))
        row = cursor.fetchone()
        return row[0] if row else None

    def delete_file(self, path: str):
        try:
            self.conn.execute("DELETE FROM files WHERE path = ?", (path,))
            self.conn.commit()
        except Exception as e:
            log.error(f"Dosya silinirken hata ({path}): {e}")

    def get_all_indexed_paths(self) -> set:
        cursor = self.conn.execute("SELECT path FROM files")
        return {row[0] for row in cursor.fetchall()}

    # -- Arama --

    def search_fts(self, match_query: str, limit: int = 100) -> list:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT f.path, f.name, f.ext, f.directory, f.size, f.mtime,
                   f.content, MIN(fts.rank)
            FROM files_fts fts
            JOIN files f ON f.id = fts.rowid
            WHERE files_fts MATCH ?
            GROUP BY f.path
            ORDER BY MIN(fts.rank)
            LIMIT ?
        """, (match_query, limit))
        return cursor.fetchall()

    def search_like(self, pattern: str, limit: int = 100) -> list:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT path, name, ext, directory, size, mtime, content
            FROM files
            WHERE normalized_content LIKE ? OR name LIKE ?
            ORDER BY mtime DESC
            LIMIT ?
        """, (pattern, pattern, limit))
        return cursor.fetchall()

    # -- Istatistikler --

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        by_ext = {}
        for row in self.conn.execute("SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY COUNT(*) DESC"):
            by_ext[row[0] or "?"] = row[1]
        return {"total": total, "by_extension": by_ext}

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
