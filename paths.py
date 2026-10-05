"""
Dosya yollari - hem normal hem paketlenmis calismada dogru sonuc verir.

Sorun:
    Path(__file__) normalde kaynak dosyanin yerini verir. Ama uygulama
    PyInstaller ile .exe haline getirildiginde __file__, programin
    gercek yerini degil PyInstaller'in acti gecici klasoru gosterir.
    Oraya yazilan dosyalar program kapaninca silinir.

Cozum:
    Paketlenmis calismada sys.executable'in (yani .exe dosyasinin)
    bulundugu klasoru kullanmak. sys.frozen ozelligi sadece
    PyInstaller altinda tanimlidir.

Iki ayri klasor kullaniyoruz:
    logs/    teknik kayit. Hata ayiklamak icin. Silinebilir.
    gecmis/  kullanici verisi. Ceviri arsivi. Silinmemeli.
"""

import sys
from pathlib import Path


def _app_dir() -> Path:
    """Uygulamanin yasadigi klasoru dondurur."""
    if getattr(sys, "frozen", False):
        # PyInstaller ile paketlenmis: .exe dosyasinin yani
        return Path(sys.executable).parent
    # Normal Python: kaynak dosyalarin yani
    return Path(__file__).parent


APP_DIR = _app_dir()
LOGS_DIR = APP_DIR / "logs"
HISTORY_DIR = APP_DIR / "gecmis"

# Klasorler yoksa olusturulur. Modul ilk ice aktarildiginda bir kez calisir.
LOGS_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)
