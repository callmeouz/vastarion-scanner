<p align="center">
  <img src="assets/logo.png" width="180" alt="Vastarion Scanner">
</p>

<h1 align="center">Vastarion Scanner</h1>
<p align="center">
  <strong>File Intelligence Engine</strong><br>
  <em>Yerel dosyalarinizi iceriklerine gore tarayan ve aninda aramanizi saglayan masaustu uygulamasi.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square" alt="Python 3.12">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square" alt="Windows">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/version-1.2.0-gold?style=flat-square" alt="v1.2.0">
</p>

---

## Ne Ise Yarar?

Vastarion Scanner, bilgisayarinizdaki **PDF, Word, Excel ve metin dosyalarinin icerigini** tarayan, indeksleyen ve milisaniye hizinda arama yapmanizi saglayan bir masaustu arama motorudur.

**Ornek:** Arama kutusuna `"Ahmet Yilmaz"` yazdiginizda, bu ismin gectigi tum dosyalari (Word, Excel, PDF), dosyanin bulundugu klasoru ve icerikteki eslesen bolumu aninda gosterir.

### Desteklenen Dosya Turleri

| Tur | Uzantilar |
|-----|-----------|
| Metin | `.txt`, `.md`, `.csv`, `.json` |
| Office | `.docx` (Word), `.xlsx` (Excel) |
| PDF | `.pdf` |
| Kod | `.py`, `.js`, `.html`, `.css` |

---

## Ozellikler

- **Full-Text Search** — SQLite FTS5 altyapisi ile milisaniye cevap suresi
- **Icerik Tarama** — Dosya adi + dosya icerigi uzerinden arama
- **Baglamsal Snippet** — Eslesen kelimenin gecen cumlesini onizleme panelinde gosterir
- **Highlight** — Eslesen kelimeler altin renkle vurgulanir
- **Klasor Yonetimi** — Taranacak klasorleri ekleyin/cikarin
- **Canli Izleme** — Dosya degisiklikleri otomatik algilanir (30sn aralikla)
- **Akilli Duplicate Engelleme** — OneDrive sync kopyalarini otomatik filtreler
- **Dosya Duzenleme** — Kurallar tanimlayarak dosyalari otomatik kategorilere ayirma
- **Guvenilirlik Puanlamasi** — Yesil (kesin eslesme) / Turuncu (olasi eslesme) gosterimi
- **Dark / Light Tema** — Iki tema arasinda aninda gecis
- **Tek EXE** — Kurulum gerektirmez, cift tikla calistir

---

## Ekran Goruntuleri

<details>
<summary>Arayuz onizlemesi</summary>

Uygulama acildiginda:
- Sol ustte Vastarion logosu
- Genis arama cubuklari
- Sonuclar tablosu: Dosya Adi | Eslesme | Konum | Tur | Boyut
- Altinda onizleme paneli (highlight ile)
- Duzenle sekmesinde kategorileme ve guvenilirlik renkleri

</details>

---

## Kurulum

### Hazir EXE (Onerilen)
```
dist/VastarionScanner.exe
```
Cift tiklayin, kullanmaya baslayin. Kurulum gerektirmez.

### Kaynak Koddan
```bash
# 1. Bagimliliklari kur
pip install -r requirements.txt

# 2. Calistir
python main.py

# 3. (Opsiyonel) EXE olustur
python build.py
```

---

## Mimari

```
vastarion-scanner/
├── main.py              # Giris noktasi
├── config.py            # Design system + tema ayarlari
├── logger.py            # Logging
├── build.py             # PyInstaller build script
│
├── core/
│   ├── search.py        # FTS5 arama motoru + snippet
│   ├── worker.py        # Arka plan indeksleme (threading)
│   ├── watcher.py       # Dosya degisiklik izleme
│   ├── scanner.py       # Dizin tarama
│   ├── organizer.py     # Dosya duzenleme + puanlama motoru
│   └── parsers.py       # Dosya icerik cikarma (docx/xlsx/pdf/txt)
│
├── db/
│   └── database.py      # SQLite + FTS5 veritabani
│
├── ui/
│   └── app.py           # CustomTkinter arayuz (dark/light tema)
│
├── utils/
│   ├── file_utils.py    # Dosya boyutu formatlama
│   └── text_utils.py    # Turkce metin normalizasyonu
│
├── assets/
│   ├── logo.png         # Vastarion logosu
│   └── logo.ico         # Windows ikon
│
└── tests/
    └── test_core.py     # Unit testler (29 test)
```

---

## Teknik Detaylar

| Bilesen | Teknoloji |
|---------|-----------|
| Dil | Python 3.12 |
| UI Framework | CustomTkinter |
| Veritabani | SQLite + FTS5 (Full-Text Search) |
| Arama | FTS5 tokenizer + LIKE fallback |
| PDF | pdfplumber |
| Word | python-docx |
| Excel | openpyxl |
| EXE | PyInstaller |

### Arama Akisi
```
Kullanici sorgu girer
    │
    ▼
normalize_turkish(sorgu)  ──  Turkce karakter normalizasyonu (I→i, Ş→s)
    │
    ▼
FTS5 MATCH '{name normalized_content} : (sorgu*)'
    │
    ▼
Sonuclar + Snippet cikarma
    │
    ▼
Duplicate filtresi (path + filename+size)
    │
    ▼
UI'da gosterim + altin highlight
```

### Puanlama Sistemi (Organizer)
```
Spesifik keyword (8+ karakter)          → +3 puan
Cok kelimeli keyword                     → +3 puan
Kisa/yaygin keyword                      → +1 puan
Dosya adinda eslesme                     → +5 puan

Score >= 5  → Kesin eslesme (yesil)
Score 2-4   → Olasi eslesme (turuncu)
Score < 2   → Elenir (minimum esik)
```

---

## Guvenlik

| Konu | Durum |
|------|-------|
| SQL Injection | Tum sorgular parameterized (`?` placeholder) |
| Dosya Erisimi | Sadece okuma — hicbir dosya degistirilmez |
| Ag Erisimi | Tamamen cevrimdisi, sunucu baglantisi yok |
| Veri Depolama | Tum veriler yerel (`~/.vastarion/`) |
| Gizlilik | Dosya icerikleri yalnizca yerel SQLite'ta saklanir |

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

**Test kapsami (29 test):**
- Turkce metin normalizasyonu (I→i, I→i)
- Snippet cikarma (baglam penceresi)
- Veritabani CRUD (ekleme, guncelleme, silme)
- FTS5 + LIKE arama
- Duplicate engelleme (path + OneDrive sync)
- Organizer puanlama mantigi
- SQL Injection korumasi
- Path traversal guvenlik testi

---

## Yol Haritasi

- [x] FTS5 tam metin arama
- [x] Icerik snippet gosterimi
- [x] Eslesme vurgulama (highlight)
- [x] OneDrive duplicate engelleme
- [x] Dark / Light tema destegi
- [x] Tek EXE dagitim
- [x] Dosya duzenleme (organizer) + sablon sistemi
- [x] Guvenilirlik puanlamasi (yesil/turuncu)
- [ ] Lazy loading (buyuk sonuc setleri icin)
- [ ] Arama gecmisi
- [ ] watchdog kutuphanesi ile gelistirilmis izleme
- [ ] Dosya onizleme (PDF thumbnail)
- [ ] Multiprocessing ile paralel tarama

---

## Gelistirici

**Oguzhan** — [@callmeouz](https://github.com/callmeouz)

Diger projeler:
- [vastarion-hunter](https://github.com/callmeouz/vastarion-hunter) — E-ticaret fiyat takip API (FastAPI + PostgreSQL + Redis)
- [vastarion-garage](https://github.com/callmeouz/vastarion-garage) — Arac yonetim sistemi (FastAPI + JWT + RBAC)
- [vastarion-queue](https://github.com/callmeouz/vastarion-queue) — Dagitik gorev kuyrugu (Redis + WebSocket dashboard)

---

## Lisans

Bu proje [MIT License](LICENSE) altinda lisanslanmistir.

Copyright (c) 2026 Oguzhan (callmeouz)
