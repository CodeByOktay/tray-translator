"""
Adim 4b - Saglayici soyutlamasi + Gemini bulut saglayicisi.

Bu dosya, ceviriyi kimin yaptigini bilen tek yerdir. Arayuz hangi
modelin veya servisin kullanildigini bilmez; sadece "cevir" der.

Yeni bir saglayici eklemek icin iki sey yeterli:
    1. Translator protokolune uyan bir sinif yaz
    2. PROVIDERS sozlugune bir satir ekle
Baska hicbir dosyaya dokunmak gerekmez.

Gemini icin onkosul:
    GEMINI_API_KEY ortam degiskeni tanimli olmali.
    Anahtar: https://aistudio.google.com  -> Get API key
"""

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Protocol

from engine import (
    GLOSSARY,
    SYSTEM_PROMPT,
    TranslationError,
    build_prompt,
    translate,
)

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class Translator(Protocol):
    """Bir cevirmenin uymasi gereken sozlesme.

    Protocol, Python'un "ordek tiplemesi"ni resmilestiren yapisidir:
    bir sinifin bu protokolden turemesi gerekmez, sadece ayni imzali
    translate() metoduna sahip olmasi yeterlidir. Boylece siniflar
    birbirinden tamamen bagimsiz kalir.
    """

    def translate(self, text: str) -> str:
        """Ingilizce metni Turkceye cevirip dondurur."""
        ...


class OllamaTranslator:
    """Yerel Ollama sunucusu uzerinden ceviri yapar.

    Asil isi translator_step1.translate() yapiyor. Bu sinif sadece
    model adini ve terim sozlugunu kendi icinde tutarak protokole
    uygun bir yuz sunuyor.
    """

    def __init__(self, model: str, terms: dict[str, str] | None = None) -> None:
        self.model = model
        self.terms = terms if terms is not None else GLOSSARY

    def translate(self, text: str) -> str:
        return translate(text, terms=self.terms, model=self.model)


class GeminiTranslator:
    """Google AI Studio (Gemini) uzerinden ceviri yapar.

    Ollama ile ayni protokole uyar, ama istek bicimi tamamen farklidir:
    Gemini sistem talimatini ayri bir alanda (system_instruction)
    bekler, kullanici metnini de "contents" listesinde tasir.

    Bu farkliligin tamami bu sinifin icinde kaliyor. Arayuz ve
    is parcacigi kodu bunlardan hicbirini bilmez.
    """

    def __init__(
        self,
        model: str = "gemini-3.6-flash",
        terms: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> None:
        self.model = model
        self.terms = terms if terms is not None else GLOSSARY
        self.timeout = timeout

    @staticmethod
    def _api_key() -> str:
        """Anahtari ortam degiskeninden okur.

        Anahtari kodun icine yazmiyoruz: dosya paylasildiginda veya
        surum kontrolune girdiginde anahtar da sizardi.
        """
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise TranslationError(
                "GEMINI_API_KEY ortam degiskeni bulunamadi. "
                "Anahtari tanimlayip PyCharm'i yeniden baslatin."
            )
        return key

    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {"parts": [{"text": build_prompt(text, self.terms)}]}
            ],
            "generationConfig": {"temperature": 0.0},
        }

        request = urllib.request.Request(
            GEMINI_ENDPOINT.format(model=self.model),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key(),
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Sunucu bir hata govdesi dondurur; icinde sebep yazar
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise TranslationError(
                f"Gemini hatasi ({exc.code}): {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TranslationError(
                "Gemini'ye baglanilamadi. Internet baglantinizi kontrol edin."
            ) from exc
        except json.JSONDecodeError as exc:
            raise TranslationError("Gemini gecersiz bir yanit dondurdu.") from exc

        return self._extract_text(body)

    @staticmethod
    def _extract_text(body: dict) -> str:
        """Yanitin derinliklerinden ceviri metnini cikarir.

        Gemini yaniti ic ice gecmis bir yapidir:
        candidates -> [0] -> content -> parts -> [0] -> text
        Her adimda .get() kullanmamizin nedeni, beklenmedik bir yanitta
        KeyError ile cokmek yerine anlasilir bir hata vermek.
        """
        candidates = body.get("candidates", [])
        if not candidates:
            reason = body.get("promptFeedback", {}).get("blockReason", "")
            raise TranslationError(
                f"Gemini bos yanit dondurdu. {reason}".strip()
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        result = "".join(part.get("text", "") for part in parts).strip()
        if not result:
            raise TranslationError("Gemini bos metin dondurdu.")
        return result


# Arayuzde gorunecek isim -> o saglayiciyi kuran fonksiyon.
# Degerler dogrudan nesne degil, nesneyi ureten fonksiyon (lambda).
# Nedeni: butun saglayicilar program acilisinda kurulmasin, sadece
# secilen kurulsun. Boylece Gemini secilmedigi surece anahtar
# aranmaz ve anahtar yoksa bile yerel ceviri sorunsuz calisir.
PROVIDERS: dict[str, Callable[[], Translator]] = {
    "Local - gemma3:1b": lambda: OllamaTranslator("gemma3:1b"),
    "Cloud - Gemini Flash": lambda: GeminiTranslator("gemini-3.6-flash"),
}

DEFAULT_PROVIDER = "Cloud - Gemini Flash"


def get_translator(name: str) -> Translator:
    """Saglayici adindan calisir haldeki cevirmen nesnesi uretir.

    Fabrika fonksiyonu deseni: arayuz "hangi saglayici secili"
    bilgisini buraya verir, hangi sinifin kurulacagina bu fonksiyon
    karar verir. Arayuz kodunda tek bir if blogu bulunmaz.
    """
    factory = PROVIDERS.get(name)
    if factory is None:
        raise ValueError(f"Bilinmeyen saglayici: {name}")
    return factory()