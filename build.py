import PyInstaller.__main__
import os
import stat
import shutil

# True = pencereli (console yok), False = console acik (hata gorunur)
WINDOWED = True


def force_remove(func, path, exc_info):
    """Windows kilitli dosya/klasor icin izin ver ve tekrar dene."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


# Eski build artifaktlarini temizle
for d in ["build", "dist"]:
    if os.path.exists(d):
        shutil.rmtree(d, onerror=force_remove)

for spec in ("vastarion.spec", "VastarionScanner.spec", "Vastarion Scanner.spec"):
    if os.path.exists(spec):
        try:
            os.remove(spec)
        except Exception:
            pass

args = [
    "main.py",
    "--name=VastarionScanner",
    "--onefile",
    "--icon=assets/logo.ico",
    "--add-data=assets;assets",
    # Core hidden importlar
    "--hidden-import=customtkinter",
    "--hidden-import=PIL",
    "--hidden-import=PIL._imagingtk",
    "--hidden-import=PIL._tkinter_finder",
    "--hidden-import=openpyxl",
    "--hidden-import=docx",
    # PDF: PyMuPDF (parsers.py 'fitz' kullaniyor)
    "--hidden-import=fitz",
    # collect-all: paketin tum kaynaklarini ve dahili importlarini topla
    "--collect-all=customtkinter",
    "--collect-all=fitz",
    "--noconfirm",
    "--clean",
]

args.append("--windowed" if WINDOWED else "--console")

# watchdog opsiyonel — kurulu ise EXE icine paketle
try:
    import watchdog  # noqa: F401
    args.append("--hidden-import=watchdog")
    args.append("--hidden-import=watchdog.observers")
    args.append("--hidden-import=watchdog.events")
    args.append("--collect-all=watchdog")
    print("[build] watchdog bulundu, EXE'ye dahil edilecek.")
except ImportError:
    print("[build] watchdog kurulu degil; polling fallback ile derleniyor.")

PyInstaller.__main__.run(args)

print("\n" + "=" * 50)
print("EXE olusturuldu: dist/VastarionScanner.exe")
if not WINDOWED:
    print("(console modu) Calistirinca konsolda hatalari gorebilirsin.")
print("=" * 50)
