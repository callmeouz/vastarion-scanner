import logging
import sys
from config import LOG_PATH

def _setup():
    """Merkezi loglama sistemini kurar."""
    logger = logging.getLogger("Vastarion")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s'))
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

log = _setup()
