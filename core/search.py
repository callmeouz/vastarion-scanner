import os
import re
import time
from utils.text_utils import normalize_turkish, tr_lower
from logger import log


# FTS5 token icinde sadece harf/rakam/altcizgi guvenli sayilir.
# Kalan karakterler (-, :, ", /, vb.) prefix-search ifadesinde hata atar.
_FTS_TOKEN_SAFE = re.compile(r"[^\w]+", re.UNICODE)


class SearchEngine:
    """FTS5 + LIKE fallback arama motoru + Snippet."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _build_fts_query(normalized: str) -> str:
        """Normalize edilmis sorguyu guvenli bir FTS5 MATCH ifadesine cevirir.

        - Ozel karakterleri temizler (FTS5'in syntax hatasi atmasini onler).
        - Cok kisa (1 karakter) tokenleri eler — prefix * gerek yok.
        - Sutun filtresi: {name normalized_content}
        """
        # Ozel karakterleri bosluga cevir, bos olanlari ele
        cleaned = _FTS_TOKEN_SAFE.sub(" ", normalized)
        tokens = [t for t in cleaned.split() if len(t) >= 2]
        if not tokens:
            return ""
        match_query = " AND ".join(f"{t}*" for t in tokens)
        return f"{{name normalized_content}} : ({match_query})"

    def search(self, query: str, limit: int = 100) -> dict:
        if not query or len(query.strip()) < 2:
            return {"elapsed_ms": 0, "count": 0, "results": []}

        start = time.perf_counter()
        normalized = normalize_turkish(query)
        fts_term = self._build_fts_query(normalized)

        results = []
        seen_paths = set()
        seen_files = set()

        # FTS5 ile arama (sorgu olusturulabildiyse)
        if fts_term:
            try:
                rows = self.db.search_fts(fts_term, limit)
                for row in rows:
                    d = self._row_to_dict(row, query)
                    if self._is_duplicate(d, seen_paths, seen_files):
                        continue
                    results.append(d)
            except Exception as e:
                log.error(f"FTS arama hatasi: {e} | sorgu='{fts_term}'")

        # Sonuc yoksa LIKE fallback
        if not results:
            try:
                # SQL LIKE wildcard'larini escape et: %, _, \
                like_safe = (
                    normalized
                    .replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                pattern = f"%{like_safe}%"
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
        """Icerikten eslesen kismi cikarip '...once [ESLESME] sonra...' seklinde dondurur."""
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
