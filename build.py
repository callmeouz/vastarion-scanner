"""
Vastarion Scanner — EXE Build Script
Kullanim: python build.py
"""
import PyInstaller.__main__
import os
import stat
import shutil

def force_remove(func, path, exc_info):
    """Windows kilitli dosya/klasor icin izin ver ve tekrar dene."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

# Temizle
for d in ["build", "dist"]:
    if os.path.exists(d):
        shutil.rmtree(d, onerror=force_remove)

spec_file = "vastarion.spec"
if os.path.exists(spec_file):
    os.remove(spec_file)

PyInstaller.__main__.run([
    "main.py",
    "--name=VastarionScanner",
    "--onefile",
    "--windowed",
    "--icon=assets/logo.ico",
    "--add-data=assets;assets",
    "--hidden-import=customtkinter",
    "--hidden-import=PIL",
    "--hidden-import=PIL._imagingtk",
    "--hidden-import=PIL._tkinter_finder",
    "--hidden-import=openpyxl",
    "--hidden-import=pdfplumber",
    "--hidden-import=docx",
    "--collect-all=customtkinter",
    "--noconfirm",
    "--clean",
])

print("\n" + "=" * 50)
print("EXE olusturuldu: dist/VastarionScanner.exe")
print("=" * 50)
