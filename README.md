<p align="center">
  <img src="assets/logo.png" width="200" alt="Vastarion Scanner Logo">
</p>

<h1 align="center">Vastarion Scanner</h1>
<p align="center">
  <strong>File Intelligence Engine</strong><br>
  <em>Bilgisayarınızdaki dosyaları hızlıca bulmanız için tasarlandı.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square" alt="Python 3.12">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square" alt="Windows">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/UI-CustomTkinter-orange?style=flat-square" alt="CustomTkinter">
</p>

---

## 🎯 Ne İşe Yarar?

Vastarion Scanner, bilgisayarınızdaki dosyaların **içeriğini** tarayan ve metin bazlı arama yapan bir masaüstü uygulamasıdır.

**Örnek senaryo:**  
Babanız "Ahmet Yılmaz" yazıyor → Uygulama, bilgisayardaki hangi Word/Excel/PDF dosyasının içinde bu ismin geçtiğini, **hangi klasörde** olduğunu ve **dosyanın neresinde** eşleştiğini gösterir.

### Desteklenen Dosya Türleri

| Tür | Uzantılar |
|-----|-----------|
| Metin | `.txt`, `.md`, `.csv`, `.json` |
| Office | `.docx` (Word), `.xlsx` (Excel) |
| PDF | `.pdf` |
| Kod | `.py`, `.js`, `.html`, `.css` |

---

## ✨ Özellikler

- 🔍 **Full-Text Search** — FTS5 altyapısı ile milisaniye cevap süresi
- 📄 **İçerik Tarama** — Dosya adı + dosya içeriği arama
- 🎯 **Snippet Gösterimi** — "...Ahmet Yılmaz maaşı güncellendi..." gibi bağlamsal eşleşme
- ✨ **Highlight** — Eşleşen kelimeler altın renkle vurgulanır
- 📁 **Klasör Yönetimi** — İstediğiniz klasörleri taramaya ekleyin/çıkarın
- 👁 **Canlı İzleme** — Watcher ile dosyalar otomatik güncellenir (30sn)
- 🧹 **Duplicate Engelleme** — OneDrive sync duplicate'lerini akıllıca filtreler
- 🎨 **Premium Dark UI** — Obsidian arka plan, altın accent, sofistike tasarım
- 📦 **Tek EXE** — Kurulum gerektirmez, çift tıkla çalıştır

---

## 🖥 Ekran Görüntüleri

<details>
<summary>Arayüz (tıkla)</summary>

Uygulama açıldığında:
- Sol üstte parlak altın Vastarion logosu
- Geniş arama çubuğu
- Sonuçlar tablosu: Dosya Adı | Eşleşme | Konum | Tür | Boyut
- Altında önizleme paneli (highlight ile)

</details>

---

## 🚀 Kurulum

### Hazır EXE (Önerilen)
```
dist/VastarionScanner.exe → Çift tıkla, kullan.
```

### Kaynak Koddan
```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. Çalıştır
python main.py

# 3. (Opsiyonel) EXE oluştur
python build.py
```

---

## 🏗 Mimari

```
vastarion-scanner/
├── main.py              # Giriş noktası
├── config.py            # Design system + ayarlar
├── logger.py            # Logging
├── build.py             # PyInstaller build script
│
├── core/
│   ├── search.py        # FTS5 arama motoru + snippet
│   ├── worker.py        # Arka plan indeksleme
│   ├── watcher.py       # Dosya değişiklik izleme
│   ├── scanner.py       # Dizin tarama
│   └── parsers.py       # Dosya içerik çıkarma (docx/xlsx/pdf/txt)
│
├── db/
│   └── database.py      # SQLite + FTS5 veritabanı
│
├── ui/
│   └── app.py           # CustomTkinter arayüz
│
├── utils/
│   ├── file_utils.py    # Dosya boyutu formatlama
│   └── text_utils.py    # Türkçe metin normalizasyonu
│
├── assets/
│   ├── logo.png         # Vastarion logosu (altın)
│   └── logo.ico         # Windows ikon
│
└── tests/
    └── test_core.py     # Unit testler
```

---

## 🔧 Teknik Detaylar

| Bileşen | Teknoloji |
|---------|-----------|
| Dil | Python 3.12 |
| UI Framework | CustomTkinter |
| Veritabanı | SQLite + FTS5 (Full-Text Search) |
| Arama | FTS5 tokenizer + LIKE fallback |
| PDF | pdfplumber |
| Word | python-docx |
| Excel | openpyxl |
| EXE | PyInstaller |

### Arama Mimarisi
```
Kullanıcı "Ahmet" yazar
    ↓
normalize_turkish("Ahmet") → "ahmet"
    ↓
FTS5 MATCH '{name normalized_content} : (ahmet*)'
    ↓
Sonuçlar + Snippet çıkarma (_extract_snippet)
    ↓
Duplicate filtresi (path + filename+size)
    ↓
UI'da gösterim + Gold highlight
```

---

## 🔒 Güvenlik

| Konu | Durum |
|------|-------|
| SQL Injection | ✅ Tüm sorgular parameterized (`?` placeholder) |
| Dosya Erişimi | ✅ Sadece okuma (read-only), yazma yok |
| Ağ Erişimi | ✅ Uygulama tamamen çevrimdışı, sunucu bağlantısı yok |
| Veri Depolama | ✅ Tüm veriler yerel (`~/.vastarion/`) |
| Gizlilik | ✅ Dosya içerikleri yalnızca yerel SQLite'ta, dışarı gönderilmez |

---

## 🧪 Testler

```bash
# Tüm testleri çalıştır
python -m pytest tests/ -v

# Sadece veritabanı testleri
python -m pytest tests/test_core.py::TestDatabase -v

# Sadece güvenlik testleri
python -m pytest tests/test_core.py::TestSecurity -v
```

**Test kapsamı:**
- Türkçe metin normalizasyonu (İ→i, I→ı)
- Snippet çıkarma (bağlam penceresi)
- Veritabanı CRUD (ekleme, güncelleme, silme)
- FTS5 + LIKE arama
- Duplicate engelleme (path + OneDrive sync)
- SQL Injection koruması

---

## 📋 Yol Haritası

- [x] FTS5 tam metin arama
- [x] İçerik snippet gösterimi
- [x] Eşleşme vurgulama (highlight)
- [x] OneDrive duplicate engelleme
- [x] Premium dark UI
- [x] Tek EXE dağıtım
- [ ] C: disk tam tarama optimizasyonu
- [ ] watchdog kütüphanesi ile gelişmiş izleme
- [ ] Arama geçmişi
- [ ] Dosya önizleme (resim, PDF thumbnail)

---

## 👨‍💻 Geliştirici

**Oğuzhan** — [@callmeouz](https://github.com/callmeouz)

Diğer projeler:
- [vastarion-garage](https://github.com/callmeouz/vastarion-garage) — FastAPI araç yönetim sistemi
- [vastarion-queue](https://github.com/callmeouz/vastarion-queue) — Mesaj kuyruk sistemi

---

## 📄 Lisans

Bu proje [MIT License](LICENSE) altında lisanslanmıştır.

```
MIT License — Copyright (c) 2026 Oğuzhan (callmeouz)
Özgürce kullanın, değiştirin ve dağıtın.
```
