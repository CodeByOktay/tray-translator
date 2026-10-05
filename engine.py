"""
Adim 1 - Ingilizce -> Turkce ceviri cekirdegi.

Onkosul: Ollama kurulu ve calisiyor olmali.
    ollama pull gemma3:4b     (veya gemma3:1b)

Calistirmak icin:
    python engine.py

Bu dosya terminalden tek basina calisabilir, ama asil isi
providers.py ve arayuz tarafindan cagrilmak.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from paths import HISTORY_DIR

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma3:1b"

SYSTEM_PROMPT = """Sen İngilizceden Türkçeye çeviri yapan bir çevirmensin.

Kurallar:
- Sadece Türkçe çevirisini yaz. Açıklama, not, alternatif verme.
- Metni yorumlama, ekleme yapma, kısaltma.
- Doğal ve akıcı Türkçe kullan; kelime kelime çevirme.
- Girdi zaten Türkçe ise olduğu gibi geri döndür.
- Girdideki biçimlendirmeyi (satır sonları, madde işaretleri) koru.
- Kaynak metindeki cümle sayısını koru, cümleleri birleştirme veya bölme.
- Aynı kelimeyi arka arkaya tekrarlama.
"""

GLOSSARY = {
    "cache": "önbellek",
    "deployment": "dağıtım",
    "endpoint": "uç nokta",
}


class TranslationError(Exception):
    """Ceviri sirasinda olusan hatalar."""


def build_prompt(text: str, terms: dict[str, str] | None) -> str:
    """Metni, varsa terim sozlugu ile birlikte istem haline getirir."""
    if not terms:
        return text

    matched = {
        en: tr for en, tr in terms.items() if en.lower() in text.lower()
    }
    if not matched:
        return text

    lines = "\n".join(f"- {en} -> {tr}" for en, tr in matched.items())
    return f"Su terimleri belirtildigi gibi cevir:\n{lines}\n\nMetin:\n{text}"


def translate(
    text: str,
    terms: dict[str, str] | None = None,
    model: str = MODEL,
    timeout: int = 60,
) -> str:
    """Ingilizce metni Turkceye cevirir.

    Args:
        text: Cevrilecek Ingilizce metin.
        terms: Zorunlu tutulacak terim eslesmeleri, orn. {"cache": "onbellek"}.
        model: Ollama model adi.
        timeout: Saniye cinsinden istek zaman asimi.

    Returns:
        Turkce ceviri.

    Raises:
        TranslationError: Ollama'ya ulasilamazsa veya yanit gecersizse.
    """
    text = text.strip()
    if not text:
        return ""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(text, terms)},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 2048},
        "keep_alive": "30m",
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # HTTPError, URLError'dan turer ve ondan ONCE yakalanmali.
        # Baglanti kuruldu ama sunucu hata dondurdu: model bulunamadi,
        # gecersiz istek gibi. Sebebi govdede yazar.
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise TranslationError(
            f"Ollama hatasi ({exc.code}): {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TranslationError(
            "Ollama'ya baglanilamadi. Servis calisiyor mu? "
            "Kontrol: ollama list"
        ) from exc
    except json.JSONDecodeError as exc:
        raise TranslationError("Ollama gecersiz bir yanit dondurdu.") from exc

    content = body.get("message", {}).get("content", "").strip()
    if not content:
        raise TranslationError("Model bos yanit dondurdu.")
    return content


def log_result(source: str, result: str, elapsed: float, model: str = MODEL) -> None:
    """Ceviriyi zaman damgasiyla birlikte gunluk log dosyasina ekler.

    Dosya adindaki tarih her cagrida yeniden hesaplanir. Modul
    seviyesinde hesaplasaydik, uygulama gece yarisini asarak acik
    kaldiginda kayitlar hala dunun dosyasina yazilirdi.
    """
    now = datetime.now()
    log_path = HISTORY_DIR / f"cikti_{now:%Y-%m-%d}.txt"

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{now:%Y-%m-%d %H:%M:%S}] model={model} sure={elapsed:.1f}sn\n")
        log_file.write(f"EN > {source}\n")
        log_file.write(f"TR > {result}\n\n")


def main() -> None:
    """Terminalden etkilesimli ceviri dongusu."""
    print(f"Model: {MODEL}  |  Cikmak icin bos satirda Enter\n")

    while True:
        try:
            text = input("EN > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break

        started = time.perf_counter()
        try:
            result = translate(text, terms=GLOSSARY)
        except TranslationError as exc:
            print(f"Hata: {exc}\n")
            continue

        elapsed = time.perf_counter() - started
        log_result(text, result, elapsed)
        print(f"TR > {result}")
        print(f"     ({elapsed:.1f} sn)\n")


if __name__ == "__main__":
    main()