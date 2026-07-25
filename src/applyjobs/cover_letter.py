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
"""
from __future__ import annotations

import datetime
import logging
from functools import lru_cache
from pathlib import Path
import re

import anthropic

from . import joblookup
from .config import COVER_LETTER_PROMPT_FILE, PROJECTS_LIST_FILE, settings
from .generator import ONSITE_WORK_MODES, BASE_RELOCATION_SENTENCE, _strip_fence
from .sheets import COL_COMPANY, COL_POZISYON, Row, SheetsClient

logger = logging.getLogger(__name__)

# Output languages. Value is what the prompt tells the model to write in.
LANGS = {"en": "English", "tr": "Turkish"}

# The exact block the letter must end with, per language. Kept here rather than in the
# prompt because the model kept dropping the name when the rule was prose ("Sign off as
# Ersin Isgor") — a letter that ends "Best regards," is one the user pastes unsigned.
SIGN_OFFS = {"en": "Best regards,\n\nErsin Isgor", "tr": "Saygılarımla,\n\nErsin Isgor"}

# The letter is short prose; this is only a ceiling. Generous because Sonnet 5's
# tokenizer emits ~30% more tokens than Sonnet 4.6 for the same text.
MAX_TOKENS = 1000

_LETTER_RE = re.compile(r"<LETTER_START>(.*?)<LETTER_END>", re.DOTALL)
# The bookkeeping header _write puts at the top of each saved letter.
_META_RE = re.compile(r"\A\s*<!--[^>]*-->\s*")


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    """Create the Anthropic client once (key from settings).

    Local to this module on purpose: importing summary_api's client would drag
    FastAPI into the CLI.
    """
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


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
    """Turn the sentence into an instruction for the prompt's rule slot."""
    if not line:
        return (
            "This job is remote, so the letter must NOT mention relocation, "
            "on-site work, or hybrid work at all."
        )
    return (
        "Place this sentence VERBATIM somewhere natural in the closing paragraph, "
        f'exactly as written and without altering or translating it: "{line}"'
    )


def _build_prompt(
    cv_md: str,
    job_description: str,
    company: str,
    job_title: str,
    lang: str,
    relocation_line: str,
) -> str:
    template = COVER_LETTER_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        template.replace("{{COMPANY}}", company)
        .replace("{{JOB_TITLE}}", job_title)
        .replace("{{JOB_DESCRIPTION}}", job_description.strip())
        .replace("{{CV}}", cv_md.strip())
        .replace("{{PROJECTS_LIST}}", PROJECTS_LIST_FILE.read_text(encoding="utf-8").strip())
        .replace("{{LANGUAGE}}", LANGS[lang])
        .replace("{{RELOCATION_RULE}}", _relocation_rule(relocation_line))
        .replace("{{SIGN_OFF}}", SIGN_OFFS[lang])
    )


def _call_model(prompt: str) -> str:
    """One plain, cheap request. Deliberately NOT generator._call_model.

    That one reads settings.claude_effort, which would fire adaptive thinking and a
    64k max_tokens ceiling at a 200-word letter. Two model-specific details here:
      * no temperature — Sonnet 5 rejects a non-default temperature/top_p/top_k with
        a 400. The letter is generated once per job, so there is no re-roll to vary;
        tone comes from the prompt file instead.
      * thinking is disabled EXPLICITLY — on Sonnet 5 an omitted `thinking` runs
        adaptive by default (same trap generator.py:150-155 documents).
    """
    message = _client().messages.create(
        model=settings.cover_letter_model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    u = getattr(message, "usage", None)
    if u is not None:
        logger.info(
            "Cover letter token usage: input=%s output=%s (model=%s)",
            getattr(u, "input_tokens", "?"),
            getattr(u, "output_tokens", "?"),
            settings.cover_letter_model,
        )
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )


def _extract_letter(full_response: str) -> str:
    """Pull the letter out of <LETTER_START>..<LETTER_END>, tolerating a stray fence."""
    m = _LETTER_RE.search(full_response)
    body = m.group(1) if m else full_response
    letter = _strip_fence(body)
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

    cv_md = _load_cv(cv_no)
    job_description = joblookup.load_saved_jd(cv_no)

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
    logger.info(
        "Generating cover letter for CV %d (%s @ %s, lang=%s, relocation=%r).",
        cv_no,
        job_title,
        company,
        lang,
        relocation_line or "(none — remote)",
    )
    prompt = _build_prompt(cv_md, job_description, company, job_title, lang, relocation_line)
    letter = _extract_letter(_call_model(prompt))
    _write(path, cv_no, lang, letter)
    logger.info("Cover letter written: %s", path)
    return letter, True
