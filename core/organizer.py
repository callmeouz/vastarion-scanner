# core/organizer.py — Akilli Dosya Duzenleme Motoru
# Taranan dosyalari iceriklerine gore kategorilere ayirip kopyalar.
# Agirlikli skor tabanlı esleme: spesifik keyword'ler daha yuksek puan alir.

import os
import shutil
import threading
from dataclasses import dataclass, field
from utils.text_utils import tr_lower
from logger import log

# ── Skor Esikleri ──────────────────────────────────────
MIN_SCORE_THRESHOLD = 2       # Bu skorun altindaki dosyalar eslesmez
SCORE_FILENAME_MATCH = 5      # Dosya adinda keyword eslesmesi
SCORE_SPECIFIC_KEYWORD = 3    # Spesifik keyword (8+ karakter veya cok kelimeli)
SCORE_COMMON_KEYWORD = 1      # Kisa/yaygin keyword

# ── Guvenilirlik Seviyeleri ────────────────────────────
CONFIDENCE_HIGH = 5           # Score >= 5 → Kesin (yesil)
CONFIDENCE_MEDIUM = 2         # Score 2-4 → Olasi (turuncu)
SPECIFIC_KEYWORD_MIN_LEN = 8  # Bu uzunluktan itibaren "spesifik" sayilir


@dataclass
class OrganizerRule:
    """Tek bir kategori kurali."""
    folder_name: str
    keywords: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "OrganizerRule":
        keywords_raw = d.get("keywords", "")
        if isinstance(keywords_raw, str):
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        else:
            keywords = list(keywords_raw)
        return cls(folder_name=d.get("folder_name", ""), keywords=keywords)


def _is_specific_keyword(keyword: str) -> bool:
    """Keyword spesifik mi? (8+ karakter veya cok kelimeli)"""
    kw = keyword.strip()
    if " " in kw:
        return True
    if len(kw) >= SPECIFIC_KEYWORD_MIN_LEN:
        return True
    return False


def _keyword_weight(keyword: str) -> int:
    """Keyword'un agirligini hesaplar."""
    return SCORE_SPECIFIC_KEYWORD if _is_specific_keyword(keyword) else SCORE_COMMON_KEYWORD


class FileOrganizer:
    """Dosyalari kurallara gore kategorize edip kopyalar."""

    def __init__(self, db, ui_queue=None):
        self.db = db
        self.ui_queue = ui_queue
        self.is_running = False
        self._thread = None

    def _emit(self, msg_type, data):
        """UI queue'ya mesaj gonderir."""
        if self.ui_queue:
            self.ui_queue.put((msg_type, data))

    # ── Esleme Kontrolu (Agirlikli Skor) ──────────────────

    @staticmethod
    def _score_file(content: str, filename: str, keywords: list) -> int:
        """
        Agirlikli skor hesaplama:
        - Dosya adinda eslesen keyword → +5 puan
        - Spesifik keyword (8+ karakter veya cok kelimeli) → +3 puan
        - Kisa/yaygin keyword → +1 puan
        - Minimum esik: 2 puan (tek kisa keyword yetmez)
        """
        if not keywords:
            return 0

        content_lower = tr_lower(content or "")
        filename_lower = tr_lower(filename or "")
        score = 0

        for keyword in keywords:
            kw = tr_lower(keyword.strip())
            if not kw:
                continue

            in_filename = kw in filename_lower
            in_content = kw in content_lower

            if not in_filename and not in_content:
                continue

            if in_filename:
                score += SCORE_FILENAME_MATCH
            elif in_content:
                score += _keyword_weight(keyword)

        return score

    @staticmethod
    def _match_file(content: str, filename: str, keywords: list) -> bool:
        """Geriye uyumluluk: minimum esigi geciyor mu?"""
        return FileOrganizer._score_file(content, filename, keywords) >= MIN_SCORE_THRESHOLD

    @staticmethod
    def get_confidence(score: int) -> str:
        """Skor'a gore guvenilirlik seviyesini dondurur."""
        if score >= CONFIDENCE_HIGH:
            return "high"     # Kesin (yesil)
        elif score >= CONFIDENCE_MEDIUM:
            return "medium"   # Olasi (turuncu)
        return "low"          # Esik altinda

    @staticmethod
    def get_confidence_label(score: int) -> str:
        """Skor'a gore kullaniciya gosterilecek etiketi dondurur."""
        conf = FileOrganizer.get_confidence(score)
        if conf == "high":
            return f"Kesin ({score})"
        elif conf == "medium":
            return f"Olasi ({score})"
        return f"Dusuk ({score})"

    # ── Onizleme (Agirlikli Skor) ───────────────────────────

    def preview(self, rules: list, include_unmatched: bool = False) -> dict:
        """
        Tum indekslenmis dosyalari kurallara gore siniflandirir.
        En yuksek skorlu kategoriye atar.
        Minimum esik: 2 puan (tek kisa keyword yetmez).
        Kopyalama YAPMAZ.
        """
        categories = {}
        for rule in rules:
            categories[rule.folder_name] = []

        unmatched = []

        cursor = self.db.conn.execute(
            "SELECT path, name, ext, content, size FROM files"
        )
        all_files = cursor.fetchall()

        for row in all_files:
            filepath, filename, ext, content, size = row
            file_info = {
                "path": filepath,
                "filename": filename,
                "ext": ext or "",
                "size": size or 0,
                "score": 0,
                "confidence": "low",
                "matched_category": ""
            }

            best_score = 0
            best_rule = None

            for rule in rules:
                score = self._score_file(content, filename, rule.keywords)
                if score > best_score:
                    best_score = score
                    best_rule = rule

            if best_score >= MIN_SCORE_THRESHOLD and best_rule:
                file_info["score"] = best_score
                file_info["confidence"] = self.get_confidence(best_score)
                file_info["matched_category"] = best_rule.folder_name
                categories[best_rule.folder_name].append(file_info)
            else:
                unmatched.append(file_info)

        for cat in categories:
            categories[cat].sort(key=lambda f: -f["score"])

        total_matched = sum(len(files) for files in categories.values())

        return {
            "categories": categories,
            "unmatched": unmatched,
            "total_matched": total_matched,
            "total_unmatched": len(unmatched)
        }

    # ── Kopyalama (Asenkron) ──────────────────────────────

    def execute(self, rules: list, target_dir: str, include_unmatched: bool = False):
        """Arka planda dosyalari kategorize edip kopyalar."""
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(
            target=self._run_copy,
            args=(rules, target_dir, include_unmatched),
            daemon=True
        )
        self._thread.start()

    def stop(self):
        self.is_running = False

    def _run_copy(self, rules: list, target_dir: str, include_unmatched: bool):
        """Dosyalari hedef klasore kopyalar."""
        try:
            self._emit("org_status", "Dosyalar siniflandiriliyor...")

            preview = self.preview(rules, include_unmatched)
            categories = preview["categories"]
            unmatched = preview["unmatched"]

            total = preview["total_matched"]
            if include_unmatched:
                total += preview["total_unmatched"]

            if total == 0:
                self._emit("org_status", "Kopyalanacak dosya bulunamadi.")
                self._emit("org_done", (0, 0, 0))
                return

            copied = 0
            errors = 0

            for folder_name, files in categories.items():
                if not self.is_running:
                    break
                if not files:
                    continue

                dest_folder = os.path.join(target_dir, folder_name)
                os.makedirs(dest_folder, exist_ok=True)

                for file_info in files:
                    if not self.is_running:
                        break

                    src = file_info["path"]
                    dst = os.path.join(dest_folder, file_info["filename"])
                    dst = self._unique_path(dst)

                    try:
                        if os.path.exists(src):
                            shutil.copy2(src, dst)
                            copied += 1
                        else:
                            log.warning(f"Dosya bulunamadi: {src}")
                            errors += 1
                    except Exception as e:
                        log.error(f"Kopyalama hatasi ({src}): {e}")
                        errors += 1

                    if copied % 5 == 0:
                        self._emit("org_progress", (copied, total, errors))

            if include_unmatched and unmatched:
                dest_folder = os.path.join(target_dir, "Diger")
                os.makedirs(dest_folder, exist_ok=True)

                for file_info in unmatched:
                    if not self.is_running:
                        break

                    src = file_info["path"]
                    dst = os.path.join(dest_folder, file_info["filename"])
                    dst = self._unique_path(dst)

                    try:
                        if os.path.exists(src):
                            shutil.copy2(src, dst)
                            copied += 1
                        else:
                            errors += 1
                    except Exception as e:
                        log.error(f"Kopyalama hatasi ({src}): {e}")
                        errors += 1

                    if copied % 5 == 0:
                        self._emit("org_progress", (copied, total, errors))

            self._emit("org_progress", (copied, total, errors))
            self._emit("org_done", (copied, total, errors))
            self._emit("org_status",
                f"Tamamlandi: {copied} dosya kopyalandi"
                + (f", {errors} hata" if errors else ""))
            log.info(f"Duzenleme tamamlandi: {copied}/{total} kopyalandi, {errors} hata")

        except Exception as e:
            log.error(f"Duzenleme hatasi: {e}")
            self._emit("org_status", f"Hata: {e}")
            self._emit("org_done", (0, 0, 0))
        finally:
            self.is_running = False

    @staticmethod
    def _unique_path(filepath: str) -> str:
        """Ayni isimde dosya varsa (1), (2) gibi numara ekler."""
        if not os.path.exists(filepath):
            return filepath

        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(f"{base} ({counter}){ext}"):
            counter += 1
        return f"{base} ({counter}){ext}"
