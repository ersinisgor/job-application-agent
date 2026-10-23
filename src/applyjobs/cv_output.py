"""cv-writer agent'ının çıktısını ayrıştırma ve satıra özel kural parçaları.

CV'yi artık bu modül değil, cv-writer subagent'ı yazıyor (.claude/agents/cv-writer.md).
Burada model çağrısı YOK; iki iş kaldı:

* Subagent'a verilecek, satıra özel kural parçalarını üretmek: SUMMARY'nin relocation
  cümlesi ve /cv-yenile'nin kullanıcı talimatı bloğu.
* Subagent'ın yazdığı analiz dosyasından CV'yi, eşleşme oranını ve öncelikli dilleri
  çıkarmak (<CV_START>…<CV_END>, <MATCH_RATE>, <LANGUAGES>).

Ayrıştırıcılar eski generator.py'dekilerle birebir aynı. Dosya biçimi bilerek
değiştirilmedi: docx_builder, check_cv_output hook'u ve önceki CV'ler aynı yoldan okunuyor.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_MATCH_RATE_RE = re.compile(r"<MATCH_RATE>\s*(\d+(?:\.\d+)?)\s*</MATCH_RATE>")

# İlanın en öncelikli iki programlama dili, örn. "Python, Java" (birincil önce).
_LANGUAGES_RE = re.compile(r"<LANGUAGES>\s*(.*?)\s*</LANGUAGES>", re.DOTALL)


BASE_RELOCATION_SENTENCE = "Open to relocation and on-site or hybrid opportunities."

# G sütununun (Uzaktan) "aday yerinde olmalı" anlamına gelen değerleri. Sheet'teki
# dropdown "Hybrit" yazıyor; diğerleri tolere edilen yazımlar. cover_letter.py ile
# paylaşılıyor, böylece iki relocation kuralı birbirinden kopamaz.
ONSITE_WORK_MODES = {"on-site", "onsite", "on site", "hybrit", "hybrid"}


def relocation_instruction(work_mode: str, city: str) -> str:
    """Satırın çalışma şekli ve şehrinden SUMMARY kapanış cümlesi kuralını üretir.

    Kural Türkçe, ama CV'ye girecek cümle İngilizce ve tırnak içinde birebir verilir:
    CV İngilizce, cümleyi model çevirmemeli.
    """
    wm = work_mode.strip().lower()
    city = city.strip()
    if wm == "remote":
        return (
            "İş UZAKTAN (remote). SUMMARY bölümünün son cümlesini "
            f'("{BASE_RELOCATION_SENTENCE}") tamamen SİL ve yerine hiçbir şey yazma.'
        )
    if wm in ONSITE_WORK_MODES:
        new_sentence = f"Open to relocation ({city}) and on-site or hybrid opportunities."
        return (
            f"İş {work_mode.strip()} (ofisten/hibrit). SUMMARY bölümünün son cümlesi "
            f'BİREBİR şöyle OLMALI: "{new_sentence}"'
        )
    return (
        "SUMMARY bölümünün son cümlesini orijinal CV'deki gibi aynen koru: "
        f'"{BASE_RELOCATION_SENTENCE}"'
    )


def extra_instruction_block(instruction: str) -> str:
    """/cv-yenile'nin serbest metin talimatını subagent'a verilecek bloğa çevirir.

    Talimat yoksa boş döner, blok hiç görünmez. Varsa BU çalışma için EN YÜKSEK öncelikli
    bir yönergedir (hangi proje çıkarılsın/öne alınsın, vurgu, sıra), ama bilerek uydurmaya
    izin VERMEZ: dürüstlük sözleşmesi geçerli kalır, talimatın andığı her proje/beceri
    gerçek olmalı (PROJE LİSTESİ'nde ya da MEVCUT CV'de). Böylece değişiklik mülakatta
    savunulabilir kalır.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return ""
    return (
        "---\n\n"
        "# ⚠️ BU ÇALIŞMAYA ÖZEL KULLANICI TALİMATI (EN YÜKSEK ÖNCELİK)\n\n"
        "SADECE bu üretim için aşağıdaki kullanıcı talimatını uygula. Seçim/yerleşim "
        "varsayılanlarıyla (hangi projelerin gireceği, sıraları, neyin öne çıkarılacağı) "
        "çelişirse talimat KAZANIR.\n\n"
        "Dürüstlük sözleşmesini EZMEZ: eklediğin ya da tuttuğun her proje, beceri veya "
        "ayrıntı GERÇEK olmalı — PROJE LİSTESİ'nde (profile/projects.md) ya da MEVCUT "
        "CV'de (profile/cv_base.md) bulunmalı. Talimat kaynakların desteklemediği bir şey "
        "isterse yalnızca gerçeklerin izin verdiği kadarını uygula ve açığı Türkçe "
        "analizinde belirt; talimatı karşılamak için asla uydurma.\n\n"
        f"KULLANICI TALİMATI:\n{instruction}\n"
    )


def strip_fence(cv: str) -> str:
    """Modelin yanlışlıkla eklediği çevreleyici ``` kod bloğunu soyar."""
    cv = cv.strip()
    if cv.startswith("```"):
        cv = re.sub(r"^```[a-zA-Z]*\n", "", cv)
        cv = re.sub(r"\n```$", "", cv).strip()
    return cv


def extract_cv(full_response: str) -> str:
    """Optimize edilmiş CV'yi <CV_START>..<CV_END> arasından çıkarır.

    Model bazen analizin içinde erkenden BAŞIBOŞ bir <CV_START> yazar ve birden çok
    başlangıç işaretçisi oluşur. İlkini almak analiz çöpünü yakalar. Bu yüzden gerçekten
    bir bölüm başlığıyla ('### ', yani gerçek CV) başlayan SON blok alınır; hiçbiri
    uymazsa son bloğa düşülür.
    """
    starts = [m.end() for m in re.finditer("<CV_START>", full_response)]
    if not starts:
        raise ValueError(
            "Could not find <CV_START>...<CV_END> markers in the model response."
        )
    blocks = []
    for s in starts:
        e = full_response.find("<CV_END>", s)
        blocks.append(full_response[s : e if e != -1 else len(full_response)])
    for body in reversed(blocks):
        cv = strip_fence(body)
        if cv.startswith("### "):
            return cv
    return strip_fence(blocks[-1])


def extract_match_rate(full_response: str) -> float | None:
    match = _MATCH_RATE_RE.search(full_response)
    if not match:
        logger.warning("No <MATCH_RATE> marker found in the model response.")
        return None
    return float(match.group(1))


def extract_languages(full_response: str) -> str:
    """İlanın en öncelikli iki programlama dilini döndürür, örn. "Python, Java".

    Modelin yazdığı <LANGUAGES>...</LANGUAGES> işaretçisinden okunur (birincil dil önce,
    ikinci alternatif sonra). İşaretçi yoksa ya da boşsa (ilan dil belirtmemişse) ""
    döner; çağıran taraf sheet hücresini boş bırakır.
    """
    match = _LANGUAGES_RE.search(full_response)
    if not match:
        logger.warning("No <LANGUAGES> marker found in the model response.")
        return ""
    # Araya karışmış boşluk/satır sonlarını temiz bir "A, B"ye indir.
    return " ".join(match.group(1).split())


def parse_agent_output(full_response: str) -> tuple[str, float | None, str]:
    """Analiz dosyasının tamamından (cv_md, match_rate, languages) üçlüsünü döndürür."""
    return (
        extract_cv(full_response),
        extract_match_rate(full_response),
        extract_languages(full_response),
    )
