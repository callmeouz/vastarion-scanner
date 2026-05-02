<p align="center">
  <img src="assets/logo.png" width="180" alt="Vastarion Scanner">
</p>

<h1 align="center">Vastarion Scanner</h1>
<p align="center">
  <strong>File Intelligence Engine</strong><br>
  <em>Yerel dosyalarinizi icerik bazli tarayan ve aninda arama yapan masaustu uygulamasi.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.2.0-C6A96B?style=flat-square" alt="v1.2.0">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square" alt="Python 3.12">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square" alt="Windows">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://github.com/callmeouz/vastarion-scanner/actions/workflows/release.yml/badge.svg" alt="Build">
</p>

---

## Ne Ise Yarar?

Vastarion Scanner, bilgisayarinizdaki **Word, Excel, PDF ve metin dosyalarinin icerigini** tarar ve anahtar kelimeye gore aninda bulur.

**Ornek:** Arama kutusuna `Ahmet Yilmaz` yazdiginizda uygulama tum indeksli dosyalarin icerigini tarar, hangi dosyada bu ismin gectigini, hangi klasorde oldugunu ve dosyanin neresinde eslestigini gosterir.

### Desteklenen Dosya Turleri

| Tur | Uzantilar |
|-----|-----------|
| Metin | `.txt`, `.md`, `.csv`, `.json` |
| Office | `.docx` (Word), `.xlsx` (Excel) |
| PDF | `.pdf` |
| Kod | `.py`, `.js`, `.html`, `.css` |

---

## Ozellikler

- **Full-Text Search** — FTS5 altyapisi ile milisaniye cevap suresi
- **Icerik Tarama** — Dosya adi + dosya icerigi uzerinden arama
- **Snippet Gosterimi** — Eslesen kismin baglam icinde onizlemesi
- **Highlight** — Eslesen kelimeler altin renkle vurgulanir
- **Klasor Yonetimi** — Istediginiz klasorleri taramaya ekleyin/cikarin
- **Canli Izleme** — watchdog (event-driven) + 30s polling fallback ile dosya degisiklikleri algilama
- **Duplicate Engelleme** — OneDrive sync kopyalarini akillica filtreler
- **Akilli Dosya Duzenleme** — Icerige gore otomatik kategorilere ayirma (kopyalama)
- **Agirlikli Puanlama** — Spesifik keyword'ler daha yuksek puan alir
- **Guvenilirlik Renkleri** — Yesil (kesin eslesme) / Turuncu (olasi eslesme)
- **Arama Gecmisi** — Son 20 aramayi saklar, tek tikla tekrar arama
- **Lazy Loading** — Buyuk sonuc setlerinde donma olmadan sayfalama
- **Dark / Light Tema** — Tek tikla gecis
- **Tek EXE** — Kurulum gerektirmez, cift tikla calistir

---

## Kurulum

### Hazir EXE (Onerilen)

[Releases](https://github.com/callmeouz/vastarion-scanner/releases) sayfasindan son surumu indirin.
Yeni bir `v*` tag'i push'landikca GitHub Actions otomatik olarak `VastarionScanner.exe` olusturup Release'e yukler.

### Kaynak Koddan

```bash
# Bagimliliklari kur
pip install -r requirements.txt

# Calistir
python main.py

# (Opsiyonel) EXE olustur
python build.py
```

---

## Mimari

```
vastarion-scanner/
├── main.py              # Giris noktasi
├── config.py            # Design system + ayarlar
├── logger.py            # Logging
├── build.py             # PyInstaller build script
│
├── core/
│   ├── search.py        # FTS5 arama motoru + snippet
│   ├── worker.py        # Arka plan indeksleme
│   ├── watcher.py       # Dosya degisiklik izleme (30s)
│   ├── scanner.py       # Dizin tarama
│   ├── organizer.py     # Icerik bazli dosya duzenleme
│   └── parsers.py       # Dosya icerik cikarma (docx/xlsx/pdf/txt)
│
├── db/
│   └── database.py      # SQLite + FTS5 veritabani
│
├── ui/
│   └── app.py           # CustomTkinter arayuz (dark/light)
│
├── utils/
│   ├── file_utils.py    # MD5 hash, boyut formatlama
│   └── text_utils.py    # Turkce metin normalizasyonu
│
├── assets/
│   ├── logo.png
│   └── logo.ico
│
└── tests/
    └── test_core.py     # Unit testler (29 test)
```

---

## Teknik Detaylar

| Bilesen | Teknoloji |
|---------|-----------|
| Dil | Python 3.12 |
| UI | CustomTkinter |
| Veritabani | SQLite + FTS5 |
| Arama | FTS5 prefix match + LIKE fallback |
| PDF okuma | PyMuPDF (fitz) |
| Word okuma | python-docx |
| Excel okuma | openpyxl |
| EXE | PyInstaller |

### Arama Akisi

```
Kullanici sorgu yazar
    │
    ▼
normalize_turkish() → Turkce karakterler duzlestrilir
    │
    ▼
FTS5 MATCH '{name normalized_content} : (kelime*)'
    │
    ▼
Sonuc yoksa → LIKE fallback (%kelime%)
    │
    ▼
Duplicate filtresi (path + filename+size)
    │
    ▼
Snippet cikarma + Gold highlight ile gosterim
```

### Puanlama Sistemi (Duzenle sekmesi)

| Kriter | Puan |
|--------|------|
| Kisa/yaygin keyword eslesmesi (ornek: burs, vize) | +1 |
| Spesifik keyword — 8+ karakter (ornek: stipendium) | +3 |
| Cok kelimeli keyword (ornek: ogrenci basvuru) | +3 |
| Dosya adinda eslesme | +5 |

Minimum esik: **2 puan**. Tek bir yaygin kelimenin gectigi alakasiz belgeler filtrelenir.

---

## Guvenlik

| Konu | Durum |
|------|-------|
| SQL Injection | Tum sorgular parameterized (`?` placeholder) |
| Dosya Erisimi | Sadece okuma — orijinal dosyalar degistirilmez |
| Ag Erisimi | Uygulama tamamen cevrimdisi, sunucu baglantisi yok |
| Veri Depolama | Tum veriler yerel (`~/.vastarion/`) |

---

## Testler

```bash
# Tum testleri calistir
python -m pytest tests/ -v

# Sadece veritabani testleri
python -m pytest tests/test_core.py::TestDatabase -v

# Sadece guvenlik testleri
python -m pytest tests/test_core.py::TestSecurity -v
```

29 test: Turkce normalizasyon, snippet cikarma, veritabani CRUD, FTS5 + LIKE arama, duplicate engelleme, puanlama sistemi, SQL injection korumasi.

---

## Yol Haritasi

- [x] FTS5 tam metin arama
- [x] Icerik snippet gosterimi + highlight
- [x] OneDrive duplicate engelleme
- [x] Dark / Light tema
- [x] Icerik bazli dosya duzenleme (organizer)
- [x] Agirlikli puanlama + guvenilirlik renkleri
- [x] Arama gecmisi
- [x] Lazy loading
- [x] Tek EXE dagitim
- [x] watchdog ile event-driven dosya izleme
- [ ] Disa aktarma (arama sonuclari CSV/TXT)
- [ ] Sistem tepsisi (arka planda calisma)
- [ ] Dosya onizleme (PDF thumbnail, resim)
- [ ] Disa aktarma (CSV / rapor)

---

## Gelistirici

**Oguzhan** — [@callmeouz](https://github.com/callmeouz)

Diger projeler:
- [vastarion-hunter](https://github.com/callmeouz/vastarion-hunter) — E-ticaret fiyat takip API'si (FastAPI + PostgreSQL + Redis)
- [vastarion-garage](https://github.com/callmeouz/vastarion-garage) — Arac yonetim sistemi (FastAPI + JWT + RBAC)
- [vastarion-queue](https://github.com/callmeouz/vastarion-queue) — Dagitik gorev kuyrugu (Redis + WebSocket dashboard)

---

## Lisans

MIT License — detaylar icin [LICENSE](LICENSE) dosyasina bakin.
