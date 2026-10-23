"""İstendiğinde üretilen mektuplar; bir ilanın zaten kaydedilmiş CV'si + ilan metninden.

Her başvuru mektup istemez; her CV'nin yanında bir mektup üretmek hiç kullanılmayan
mektuplara para/kota yakardı. Bu modül istek üzerine bir tane üretir.

Burada bir şey değiştirmeden önce bilinmesi gereken üç şey:

* **Dosyanın kendisi önbellektir.** Bir mektup cover_letter_<no>_<lang>.md'de durur ve
  varlığı tek "zaten yapıldı" kaydıdır — önbellek dosyası yok, sürüm damgası yok, sheet'te
  hiçbir şey yok. get_or_create() modeli çağırmak yerine onu yeniden okur; yalnızca
  force=True yeniden üretir. Kimlik dili de içerir, çünkü EN ve TR iki farklı çıktıdır (EN
  üretildikten sonra TR istemek EN mektubu sessizce geri vermemeli).
* **pipeline import yok.** summary_api bu modülü import eder ve pipeline Playwright'ı
  modül düzeyinde çeker — bkz. joblookup.py.
* **Mektubu bir agent yazar.** Önbellekte yoksa get_or_create() `claude -p "/mektup <no>
  <lang>"` çalıştırır (agent_runner) ve cover-letter-writer agent'ının cv-tools MCP
  sunucusu üzerinden kaydettiği dosyayı (save_cover_letter) geri okur.
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
import re

from . import agent_runner, joblookup
from .config import PROJECTS_LIST_FILE, settings
from .cv_output import ONSITE_WORK_MODES, BASE_RELOCATION_SENTENCE, strip_fence
from .sheets import COL_COMPANY, COL_POZISYON, Row, SheetsClient

logger = logging.getLogger(__name__)

# Çıktı dilleri. Değer, agent'a mektubun hangi dilde yazılacağını söyleyen addır.
LANGS = {"en": "English", "tr": "Turkish"}

# Mektubun bitmesi gereken birebir blok, dil başına. Prompt yerine burada tutuluyor, çünkü kural
# düzyazıyken ("Ersin Isgor olarak imzala") model adı düşürüp duruyordu — "Best regards," ile
# biten bir mektup, kullanıcının imzasız yapıştırdığı mektuptur.
SIGN_OFFS = {"en": "Best regards,\n\nErsin Isgor", "tr": "Saygılarımla,\n\nErsin Isgor"}

_LETTER_RE = re.compile(r"<LETTER_START>(.*?)<LETTER_END>", re.DOTALL)
# _write'ın kaydedilen her mektubun başına koyduğu kayıt başlığı.
_META_RE = re.compile(r"\A\s*<!--[^>]*-->\s*")


def cover_letter_path(cv_no: int, lang: str) -> Path:
    """Bir mektubun durduğu yer. Yalnızca birebir yol — bu klasörde ASLA glob yapma: el yapımı
    eski mektuplar (cover_letter_117_fs.docx ve benzerleri) de burada.
    """
    return settings.cover_letter_dir / f"cover_letter_{cv_no}_{lang}.md"


def _load_cv(cv_no: int) -> str:
    """Bu ilan için uyarlanmış CV Markdown'u.

    CV'ler yalnızca No. 200'den itibaren var; altında ne CV ne de kaydedilmiş ilan metni
    tutuldu, yani mektup hiçbir şeye dayandırılamaz.
    """
    cv_path = settings.markdown_dir / f"cv_{cv_no}.md"
    if not cv_path.exists():
        raise FileNotFoundError(
            f"CV {cv_no} için üretilmiş CV bulunamadı: {cv_path} "
            f"(200'den küçük CV'ler için mektup üretilemiyor)."
        )
    cv_md = cv_path.read_text(encoding="utf-8").strip()
    if not cv_md:
        raise ValueError(f"CV {cv_no} dosyası boş: {cv_path}")
    return cv_md


# Türkçe yönelme hâli eki ("-a"/"-e", ünlüden sonra "y" kaynaştırmasıyla), kelimenin son
# ünlüsüne göre seçilir. Sabit bir ek, gerçekte geçen şehirlerin çoğu için yanlış olurdu:
# İstanbul'a, Ankara'ya, İzmir'e, Gaziantep'e.
_TR_BACK_VOWELS = "aıouâû"
_TR_FRONT_VOWELS = "eiöü"
_TR_VOWELS = _TR_BACK_VOWELS + _TR_FRONT_VOWELS


def _tr_dative(name: str) -> str:
    """Özel ad + Türkçe yönelme eki, ör. "İstanbul" -> "İstanbul'a", "Ankara" -> "Ankara'ya"."""
    lowered = name.lower()
    last_vowel = next((ch for ch in reversed(lowered) if ch in _TR_VOWELS), "")
    suffix = "a" if last_vowel in _TR_BACK_VOWELS else "e"
    buffer = "y" if lowered and lowered[-1] in _TR_VOWELS else ""
    return f"{name}'{buffer}{suffix}"


# Relocation cümlesi, dil başına. Türkçe mektuplar Türkçe bir cümle alır: başka her yeri Türkçe
# olan bir mektuba bırakılmış İngilizce bir cümle, onu okuyan (Türk) işverene kopyala-yapıştır
# artığı gibi okunur.
_RELOCATION_BASE = {
    "en": BASE_RELOCATION_SENTENCE,
    "tr": "Relokasyona ve ofisten veya hibrit çalışmaya açığım.",
}


def _relocation_city_line(city: str, lang: str) -> str:
    if lang == "tr":
        return f"{_tr_dative(city)} reloke olmaya ve ofisten veya hibrit çalışmaya açığım."
    return f"Open to relocation ({city}) and on-site or hybrid opportunities."


def _relocation_line(work_mode: str, city: str, lang: str) -> str:
    """Mektuba konacak relocation cümlesi, ya da hiç konmayacaksa "".

    cv_output.relocation_instruction'ın üç dalını yansıtır ve sheet verisi burada da bunun
    doğru karar olduğunu söylüyor: ofisten/hibrit satırlarda F sütunu her zaman gerçek bir
    şehir (İstanbul/Ankara/İzmir/Gaziantep), "Türkiye"/"EMEA" değerleri ise yalnızca remote
    ya da çalışma şekli boş satırlarda görünüyor — orada şehir yazılmıyor.
    """
    wm = work_mode.strip().lower()
    city = city.strip()
    if wm == "remote":
        return ""
    if wm in ONSITE_WORK_MODES and city:
        return _relocation_city_line(city, lang)
    return _RELOCATION_BASE[lang]


def _relocation_rule(line: str) -> str:
    """Cümleyi agent'a verilecek kurala çevirir (kural Türkçe, cümle birebir)."""
    if not line:
        return (
            "Bu iş uzaktan (remote); mektup relocation'dan, ofisten çalışmadan ya da "
            "hibrit çalışmadan HİÇ söz etmemeli."
        )
    return (
        "Şu cümleyi kapanış paragrafında doğal bir yere BİREBİR koy; değiştirme, "
        f'çevirme: "{line}"'
    )


def _extract_letter(full_response: str) -> str:
    """Mektubu <LETTER_START>..<LETTER_END> arasından çıkarır; başıboş bir kod bloğunu tolere eder."""
    m = _LETTER_RE.search(full_response)
    body = m.group(1) if m else full_response
    letter = strip_fence(body)
    if not letter:
        raise ValueError("Model returned an empty cover letter.")
    return letter


def _write(path: Path, cv_no: int, lang: str, letter: str) -> None:
    """Atomik yazar (geçici dosya + replace), böylece eşzamanlı bir okuyucu asla yarım dosya görmez.

    Mektup ikinci bir süreç tarafından okunur (API, agent'ın yazdığını sunar); bu yüzden
    summary_api._save_cache'in yolunu izler.
    """
    stamp = datetime.date.today().isoformat()
    header = f"<!-- cv_no: {cv_no} | lang: {lang} | model: {settings.cover_letter_model} | {stamp} -->"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(f"{header}\n\n{letter}\n", encoding="utf-8")
    tmp.replace(path)


def _read_letter(path: Path) -> str:
    """Mektup gövdesi, _write'ın eklediği kayıt başlığı olmadan.

    Başlık yalnızca diske ait bir ayrıntı: her çağıran, kullanıcının doğrudan başvuru formuna
    yapıştırabileceği metni ister.
    """
    return _META_RE.sub("", path.read_text(encoding="utf-8"), count=1).strip()


def letter_inputs(cv_no: int, lang: str, row: Row | None = None) -> dict:
    """Mektup agent'ının ihtiyaç duyduğu her şeyi toplar ve eksik varsa erkenden durur.

    İki yer kullanır: get_or_create (agent'ı boşuna başlatmamak için ön kontrol) ve
    cv-tools MCP sunucusunun cover_letter_context aracı (agent'a girdiyi vermek için).
    Böylece kontroller ve relocation kuralı tek yerde kalır.

    Raises FileNotFoundError / ValueError with user-facing Turkish messages.
    """
    if lang not in LANGS:
        raise ValueError(f"Bilinmeyen dil: {lang!r} (geçerli: {', '.join(LANGS)})")
    _load_cv(cv_no)  # CV yoksa ya da boşsa burada anlaşılır mesajla durur
    joblookup.load_saved_jd(cv_no)

    if row is None:
        rows = SheetsClient().get_rows()
        row = joblookup.find_row_for_cv_no(rows, cv_no)
        if row is None:
            raise FileNotFoundError(f"CV No {cv_no} sheet'te bulunamadı.")

    company = row.get(COL_COMPANY)
    job_title = row.get(COL_POZISYON)
    if not company or not job_title:
        # Yanlış (ya da eksik) şirket adıyla bir mektup değersizdir ve CV'nin aksine güvenle düşülecek
        # bir şey yok. Tahmin etmek yerine bunu söyle.
        raise ValueError(
            f"CV {cv_no}: sheet satır {row.number}'de şirket (J) veya pozisyon (L) boş — "
            f"mektup üretilemez. Önce o hücreleri doldurun."
        )

    relocation_line = _relocation_line(row.work_mode, row.city, lang)
    return {
        "cv_no": cv_no,
        "lang": lang,
        "language": LANGS[lang],
        "company": company,
        "job_title": job_title,
        "cv_path": str(settings.markdown_dir / f"cv_{cv_no}.md"),
        "job_description_path": str(
            settings.job_description_dir / f"job_description_{cv_no}.md"
        ),
        "projects_path": str(PROJECTS_LIST_FILE),
        "relocation_line": relocation_line,
        "relocation_rule": _relocation_rule(relocation_line),
        "sign_off": SIGN_OFFS[lang],
        "output_path": str(cover_letter_path(cv_no, lang)),
    }


def save_letter(cv_no: int, lang: str, text: str) -> Path:
    """Agent'ın yazdığı mektubu doğrulayıp diske yazar (cv-tools.save_cover_letter).

    İmza bloğu birebir SIGN_OFFS[lang] ile bitmeli: düzyazı kuralı ("Ersin Isgor olarak
    imzala") zaman zaman yok sayılıyordu ve imzasız mektup forma öyle yapıştırılıyordu.
    """
    if lang not in LANGS:
        raise ValueError(f"Bilinmeyen dil: {lang!r} (geçerli: {', '.join(LANGS)})")
    letter = _extract_letter(text)
    if not letter.rstrip().endswith(SIGN_OFFS[lang]):
        raise ValueError(
            "Mektup imza bloğuyla birebir bitmeli:\n" + SIGN_OFFS[lang]
        )
    path = cover_letter_path(cv_no, lang)
    _write(path, cv_no, lang, letter)
    logger.info("Cover letter written: %s", path)
    return path


def get_or_create(
    cv_no: int,
    lang: str = "en",
    force: bool = False,
    row: Row | None = None,
) -> tuple[str, bool]:
    """(letter, created) döndürür — yalnızca mektup gövdesi, yapıştırmaya hazır.

    created=False, mektubun diskten geldiği ve model çağrısı yapılmadığı anlamına gelir.
    Çağıran zaten satıra sahipse (API öyle) ikinci bir sheet indirmesini atlamak için `row`
    geçir.

    Kullanıcıya yönelik Türkçe mesajlarla FileNotFoundError / ValueError fırlatır; çağıranlar
    bunları 404'e eşler. Agent çalışıp dosya üretmezse RuntimeError fırlatır.
    """
    if lang not in LANGS:
        raise ValueError(f"Bilinmeyen dil: {lang!r} (geçerli: {', '.join(LANGS)})")

    path = cover_letter_path(cv_no, lang)
    if not force and path.exists():
        logger.info("Cover letter cache hit: %s", path)
        return _read_letter(path), False

    # Ön kontrol: eksik CV / ilan metni / şirket adı varsa agent'ı hiç başlatma.
    inputs = letter_inputs(cv_no, lang, row=row)
    logger.info(
        "Generating cover letter for CV %d (%s @ %s, lang=%s) via the cover-letter agent.",
        cv_no,
        inputs["job_title"],
        inputs["company"],
        lang,
    )
    before = path.stat().st_mtime_ns if path.exists() else None
    result = agent_runner.run_cover_letter(cv_no, lang, force=force)
    after = path.stat().st_mtime_ns if path.exists() else None
    if after is None or after == before:
        raise RuntimeError(
            f"Mektup agent'ı CV {cv_no} ({lang}) için dosya üretmedi: "
            f"{result.text or 'ayrıntı için state/agent.log'}"
        )
    return _read_letter(path), True
