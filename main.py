import sys
import os

# Proje kok dizinini Python path'ine ekle
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ui.app import VastarionApp
from logger import log


def main():
    log.info("Vastarion Scanner baslatiliyor...")
    try:
        app = VastarionApp()
        app.mainloop()
    except Exception as e:
        log.critical(f"Uygulama coktu: {e}", exc_info=True)


if __name__ == "__main__":
    main()
