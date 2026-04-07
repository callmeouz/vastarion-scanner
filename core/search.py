import os
import time
from utils.text_utils import normalize_turkish, tr_lower
from logger import log


class SearchEngine:
    """FTS5 + LIKE fallback arama motoru + Snippet."""

    def __init__(self, db):
        self.db = db

    def search(self, query: str, limit: int = 100) -> dict:
        if not query or len(query.strip()) < 2:
            return {"elapsed_ms": 0, "count": 0, "results": []}

        start = time.perf_counter()
        normalized = normalize_turkish(query)
        words = normalized.split()
        match_query = " AND ".join([f"{w}*" for w in words])
        fts_term = f"{{name normalized_content}} : ({match_query})"

        results = []
        seen_paths = set()
        seen_files = set()

        # FTS5 ile arama
        try:
            rows = self.db.search_fts(fts_term, limit)
            for row in rows:
                d = self._row_to_dict(row, query)
                if self._is_duplicate(d, seen_paths, seen_files):
                    continue
                results.append(d)
        except Exception as e:
            log.error(f"FTS arama hatasi: {e}")

        # Sonuc yoksa LIKE fallback
        if not results:
            try:
                pattern = f"%{normalized}%"
                rows = self.db.search_like(pattern, limit)
                for row in rows:
                    d = self._row_to_dict(row, query)
                    if self._is_duplicate(d, seen_paths, seen_files):
                        continue
                    results.append(d)
            except Exception as e:
                log.error(f"LIKE arama hatasi: {e}")

        elapsed = int((time.perf_counter() - start) * 1000)
        return {"elapsed_ms": elapsed, "count": len(results), "results": results}

    @staticmethod
    def _extract_snippet(content: str, query: str, width: int = 50) -> str:
        """Icerikten eslesen kismi cikarip '...önce [ESLESME] sonra...' seklinde dondurur."""
        if not content:
            return ""

        query_lower = tr_lower(query)
        content_lower = tr_lower(content)

        # Ilk bulunan satiri bul
        best_line = ""
        best_pos = -1
        for line in content.split("\n"):
            pos = tr_lower(line).find(query_lower)
            if pos != -1:
                best_line = line.strip()
                best_pos = pos
                break

        if best_pos == -1:
            # Kelime kelime dene
            for word in query.split():
                if len(word) < 2:
                    continue
                for line in content.split("\n"):
                    if tr_lower(word) in tr_lower(line):
                        return f"...{line.strip()[:100]}..."
            return ""

        # Eslesen kismin etrafini kes
        start = max(0, best_pos - width)
        end = min(len(best_line), best_pos + len(query) + width)
        snippet = best_line[start:end].strip()

        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(best_line) else ""
        return f"{prefix}{snippet}{suffix}"

    @staticmethod
    def _is_duplicate(d, seen_paths, seen_files):
        norm_path = os.path.normpath(d["filepath"]).lower()
        if norm_path in seen_paths:
            return True
        seen_paths.add(norm_path)

        file_key = (d["filename"].lower(), d["size"])
        if file_key in seen_files:
            return True
        seen_files.add(file_key)
        return False

    @staticmethod
    def _row_to_dict(row, query="") -> dict:
        content = row[6] if len(row) > 6 else ""
        return {
            "filepath": row[0],
            "filename": row[1],
            "ext": row[2] or "",
            "directory": row[3] or "",
            "size": row[4],
            "modified": row[5],
            "snippet": SearchEngine._extract_snippet(content or "", query),
        }
