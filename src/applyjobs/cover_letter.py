"""On-demand cover letters, generated from a job's already-saved CV + job description.

Only some applications ask for a cover letter, so producing one alongside every CV
would burn money on letters that are never used. This module makes one on request.

Two things worth knowing before changing anything here:

* **The file IS the cache.** A letter lives at cover_letter_<no>_<lang>.md, and its
  existence is the only "already done" record — there is no cache file, no version
  stamp, and nothing in the sheet. get_or_create() re-reads it instead of calling the
  model; only force=True regenerates. Identity includes the language, because EN and
  TR are two different artifacts (asking for TR after generating EN must not silently
  hand back the EN letter).
* **No pipeline import.** summary_api imports this module, and pipeline pulls in
  Playwright at module scope — see joblookup.py.
* **The letter is written by an agent.** On a cache miss get_or_create() runs
  `claude -p "/mektup <no> <lang>"` (agent_runner) and reads back the file that the
  cover-letter-writer agent saved through the cv-tools MCP server (save_cover_letter).
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

# Output languages. Value is what the prompt tells the model to write in.
LANGS = {"en": "English", "tr": "Turkish"}

# The exact block the letter must end with, per language. Kept here rather than in the
# prompt because the model kept dropping the name when the rule was prose ("Sign off as
# Ersin Isgor") — a letter that ends "Best regards," is one the user pastes unsigned.
SIGN_OFFS = {"en": "Best regards,\n\nErsin Isgor", "tr": "Saygılarımla,\n\nErsin Isgor"}

_LETTER_RE = re.compile(r"<LETTER_START>(.*?)<LETTER_END>", re.DOTALL)
# The bookkeeping header _write puts at the top of each saved letter.
_META_RE = re.compile(r"\A\s*<!--[^>]*-->\s*")


def cover_letter_path(cv_no: int, lang: str) -> Path:
    """Where a letter lives. Exact path only — NEVER glob this directory: the legacy
    hand-made letters (cover_letter_117_fs.docx and friends) share it."""
    return settings.cover_letter_dir / f"cover_letter_{cv_no}_{lang}.md"


def _load_cv(cv_no: int) -> str:
    """The tailored CV markdown for this job.

    CVs only exist from No. 200 up; below that neither the CV nor the saved job
    description was kept, so a letter cannot be grounded in anything.
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


# Turkish dative suffix ("-a"/"-e", with a "y" buffer after a vowel), chosen by the
# last vowel of the word. A fixed suffix would be wrong for most of the cities that
# actually occur: İstanbul'a, Ankara'ya, İzmir'e, Gaziantep'e.
_TR_BACK_VOWELS = "aıouâû"
_TR_FRONT_VOWELS = "eiöü"
_TR_VOWELS = _TR_BACK_VOWELS + _TR_FRONT_VOWELS


def _tr_dative(name: str) -> str:
    """Proper noun + Turkish dative, e.g. "İstanbul" -> "İstanbul'a", "Ankara" -> "Ankara'ya"."""
    lowered = name.lower()
    last_vowel = next((ch for ch in reversed(lowered) if ch in _TR_VOWELS), "")
    suffix = "a" if last_vowel in _TR_BACK_VOWELS else "e"
    buffer = "y" if lowered and lowered[-1] in _TR_VOWELS else ""
    return f"{name}'{buffer}{suffix}"


# The relocation sentence, per language. Turkish letters get a Turkish sentence: an
# English one dropped into an otherwise-Turkish letter reads as a copy-paste artifact
# to the (Turkish) employer reading it.
_RELOCATION_BASE = {
    "en": BASE_RELOCATION_SENTENCE,
    "tr": "Relokasyona ve ofisten veya hibrit çalışmaya açığım.",
}


def _relocation_city_line(city: str, lang: str) -> str:
    if lang == "tr":
        return f"{_tr_dative(city)} reloke olmaya ve ofisten veya hibrit çalışmaya açığım."
    return f"Open to relocation ({city}) and on-site or hybrid opportunities."


def _relocation_line(work_mode: str, city: str, lang: str) -> str:
    """The relocation sentence to put in the letter, or "" to leave it out.

    Mirrors generator._relocation_instruction's three branches, and the sheet data
    says that is the right call here too: for on-site/hybrid rows column F is always
    a real city (İstanbul/Ankara/İzmir/Gaziantep), while the "Türkiye"/"EMEA" values
    only ever appear on remote or blank-work-mode rows — where no city is printed.
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
    """Pull the letter out of <LETTER_START>..<LETTER_END>, tolerating a stray fence."""
    m = _LETTER_RE.search(full_response)
    body = m.group(1) if m else full_response
    letter = strip_fence(body)
    if not letter:
        raise ValueError("Model returned an empty cover letter.")
    return letter


def _write(path: Path, cv_no: int, lang: str, letter: str) -> None:
    """Write atomically (temp + replace) so a concurrent reader never sees a half file.

    The letter is read by a second process (the API serves what the CLI wrote), which
    is why this follows summary_api._save_cache rather than pipeline._save_outputs.
    """
    stamp = datetime.date.today().isoformat()
    header = f"<!-- cv_no: {cv_no} | lang: {lang} | model: {settings.cover_letter_model} | {stamp} -->"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(f"{header}\n\n{letter}\n", encoding="utf-8")
    tmp.replace(path)


def _read_letter(path: Path) -> str:
    """The letter body, without the bookkeeping header _write adds.

    The header is a disk-only detail: every caller wants text the user can paste
    straight into an application form.
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
        # A letter with the wrong (or a missing) company name is worthless, and unlike
        # the CV there is nothing safe to fall back on. Say so instead of guessing.
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
    """Return (letter, created) — the letter body only, ready to paste.

    created=False means it came off disk and no model call was made. Pass `row` when
    the caller already has it (the API does) to skip a second sheet download.

    Raises FileNotFoundError / ValueError with user-facing Turkish messages; callers
    map those to a 404.
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
