"""
Hata gunlugu - yakalanmamis tum hatalari dosyaya yazar.

Neden gerekli:
    Uygulama pythonw.exe veya paketlenmis .exe ile calistiginda konsol
    penceresi yoktur. Bir hata olustugunda program sessizce olur ve
    sebebini goremezsin. Bu modul hatalari logs/hata.log dosyasina
    yazarak bu korlugu ortadan kaldirir.

Kullanim:
    import logsetup
    logsetup.install()      # main() cagrilmadan once, bir kez
"""

import logging
import logging.handlers
import sys
import threading

from paths import LOGS_DIR

LOG_PATH = LOGS_DIR / "hata.log"

# Dosya bu boyuta ulasinca yenisi acilir, eskisi hata.log.1 olur.
MAX_BYTES = 1_000_000      # ~1 MB
BACKUP_COUNT = 3           # en fazla 3 eski dosya saklanir


def install() -> None:
    """Hata gunlugunu kurar ve yakalama kancalarini yerlestirir."""
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Ana is parcacigindaki yakalanmamis hatalar
    sys.excepthook = _handle_exception
    # Arka plandaki is parcaciklarindaki hatalar (pynput dinleyicisi,
    # ceviri worker'i). Bunlar sys.excepthook'a dusmez, ayri kanca ister.
    threading.excepthook = _handle_thread_exception

    logging.info("Uygulama basladi")


def _handle_exception(exc_type, exc_value, exc_traceback) -> None:
    """Ana is parcaciginda yakalanmamis hata olustugunda cagrilir."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Ctrl+C normal bir cikis yoludur, hata olarak kaydetme
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical(
        "Yakalanmamis hata",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def _handle_thread_exception(args) -> None:
    """Arka plan is parcaciginda yakalanmamis hata olustugunda cagrilir."""
    logging.critical(
        "Is parcaciginda yakalanmamis hata",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
