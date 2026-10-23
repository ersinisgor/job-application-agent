"""CV hattının deterministik adımları: aday satır seçimi, ilan okuma, çıktı kaydetme,
Google Doc/PDF dışa aktarımı.

Burada model çağrısı YOK. CV'yi /cv-uret command'ı ile cv-writer subagent'ı üretir;
bu modüldeki fonksiyonları ise cv-tools MCP sunucusu (mcp_server.py) ve poller döngüsü
(main.py) çağırır. Değişmez kurallar (iki koşullu tetik, tekrar kontrolü, Kalkmış
işaretçisi, numaralandırma tabanı) bilerek burada, Python'da duruyor: LLM akışı yönetir
ama bu kuralları değiştiremez.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import docx_builder, drive_docs, huntr, joblookup
from .reporting import record_duplicate, record_failure
from .config import (
    CV_TRIGGER_BASVURU_VALUES,
    HUNTR_SEEN_FILE,
    NO_CV_MARKER,
    STATE_DIR,
    settings,
)
from .scraper import JobPage, Scraper
from .sheets import Row, SheetsClient

logger = logging.getLogger(__name__)

# Highest CV number ever assigned. Acts as a floor so a transient bad read of the
# sheet can never reset numbering to a low value and clobber existing CVs.
LAST_CV_FILE = STATE_DIR / "last_cv_no"


def load_last_cv_no() -> int:
    try:
        return int(LAST_CV_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def save_last_cv_no(value: int) -> None:
    LAST_CV_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_CV_FILE.write_text(str(value), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Huntr import
# --------------------------------------------------------------------------- #

# Consecutive scans where the board returned no jobs. After a couple in a row we alert
# once (likely an expired Huntr session), but a single transient empty read is ignored.
_huntr_empty_streak = 0


def _norm_url(url: str) -> str:
    return url.split("?", 1)[0].strip()


# LinkedIn job id inside the link, e.g. .../jobs/view/4427414076/... -> 4427414076.
# This is exactly what column M (İlan Numarası) extracts from K via its formula.
_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)")


def _job_key(link: str) -> str:
    """Stable per-posting identity for de-duplication.

    For LinkedIn links it is the job id (the value column M computes from K) — the
    most reliable signal, since the same posting can have many tracking URLs. For
    non-LinkedIn links it falls back to the query-stripped URL. Empty link -> "".

    We derive the id from K rather than reading column M directly: M is a spreadsheet
    formula, so openpyxl returns the formula text (and Google's cached value can be
    missing for a freshly appended row) — computing it from K is equivalent and robust.
    """
    if not link:
        return ""
    m = _LINKEDIN_ID_RE.search(link)
    if m:
        return f"li:{m.group(1)}"
    return f"url:{_norm_url(link)}"


def load_huntr_seen() -> set[str] | None:
    """Board job keys already processed. None means 'first run' (no baseline yet)."""
    if not HUNTR_SEEN_FILE.exists():
        return None
    try:
        return set(json.loads(HUNTR_SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def save_huntr_seen(keys: set[str]) -> None:
    HUNTR_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    HUNTR_SEEN_FILE.write_text(json.dumps(sorted(keys)), encoding="utf-8")


def sync_huntr_to_sheet() -> int:
    """Import newly-saved Huntr board jobs into the sheet. Returns rows appended.

    OFF by default now — the extension panel's "Ekle" button (summary_api's /add-job) is
    the primary "new job -> sheet row" source. This stays here, inert, unless
    HUNTR_BOARD_URL is set again.

    Identity is the job id (column M / _job_key), not createdAt. We keep a persisted set
    of board job keys we've already handled ('seen'). Each scan, a key that newly appears
    on the board is either:
      - imported (not in the sheet yet), or
      - flagged as a DUPLICATE (already in the sheet — no CV produced; the user is alerted
        via record_duplicate), then marked seen so it's only reported once.
    First run baselines the current board (imports nothing, no backlog dump).
    """
    if not settings.huntr_board_url:
        return 0

    global _huntr_empty_streak
    jobs = huntr.HuntrClient(headless=True).fetch_jobs()
    if not jobs:
        _huntr_empty_streak += 1
        logger.info("Huntr: no jobs found on the board.")
        if _huntr_empty_streak == 2:  # alert once; ignore a single transient empty read
            record_failure(
                "huntr_board",
                error="Board okunamadı — Huntr oturumu kapanmış olabilir. "
                "Çalıştır: ./.venv/bin/python scripts/huntr_login.py",
            )
        return 0
    _huntr_empty_streak = 0

    board_keys = {_job_key(j["url"]) for j in jobs if j.get("url")}
    seen = load_huntr_seen()
    first_run = seen is None

    # Fast path: established run with nothing new on the board -> no need to read the sheet.
    if not first_run and not (board_keys - seen):
        logger.info("Huntr: no new jobs to import.")
        return 0

    sheets = SheetsClient()
    existing_by_key: dict[str, int] = {}
    for r in sheets.get_rows():
        if r.link:
            existing_by_key.setdefault(_job_key(r.link), r.number)

    if first_run:
        # First run / migration: baseline ONLY the board jobs already tracked in the sheet,
        # so we don't spam duplicate alerts for the backlog. Board jobs NOT in the sheet stay
        # unseen and are imported below — genuinely pending jobs are never swallowed.
        seen = board_keys & existing_by_key.keys()
        logger.info("Huntr first run: baselined %d board job(s) already in the sheet.", len(seen))

    # In info-only mode we save the job info straight from Huntr (reliable, captured at
    # save time) and mark N so no CV is produced — instead of re-scraping the job page,
    # which is often an expired/stale LinkedIn view that yields wrong or missing fields.
    info_only = not settings.cv_generation

    new_keys = board_keys - seen  # jobs we haven't handled yet
    to_import: list[dict] = []
    for j in jobs:
        key = _job_key(j["url"])
        if key not in new_keys:
            continue
        if key in existing_by_key:
            # Newly added to Huntr but already tracked in the sheet -> alert, don't import.
            record_duplicate(j["url"], key, existing_by_key[key])
            continue
        entry = {"url": j["url"]}
        if info_only:
            # Fill only the reliable identity fields (company J, title L) from Huntr's
            # own record — NOT a re-scrape. City is intentionally left blank: Huntr's
            # geocoded location is often wrong (e.g. "Krizan Bay"), so F/H/C are left
            # for the user to fill rather than writing bad data.
            entry["company"] = j.get("company", "")
            entry["title"] = j.get("title", "")
        to_import.append(entry)

    # Mark everything currently on the board as handled so each job is processed once.
    save_huntr_seen(set(seen) | board_keys)

    if not to_import:
        logger.info("Huntr: no new jobs to import (newly-seen ones were duplicates).")
        return 0

    marker = NO_CV_MARKER if info_only else None
    written = sheets.append_job_rows(to_import, cv_no_marker=marker)
    logger.info(
        "Huntr: imported %d new job(s) into rows %s%s.",
        len(written), written, " (info-only, no CV)" if info_only else "",
    )
    return len(written)


def is_candidate(row: Row) -> bool:
    """A row needs a CV when it has a link, no CV No yet, and B says "Üretilecek".

    Two conditions, not one. Column N (CV No) still answers "was this already made?" —
    filled = done, empty = to do — which is what makes 'delete row + re-add the same job'
    work. But an empty N is no longer enough to spend a generation: the Başvuru column (B)
    has to carry a CV_TRIGGER_BASVURU_VALUES value, which the user sets when actually
    applying. A row added from the panel arrives with B empty and simply waits.
    """
    if not row.link:
        return False
    if row.cv_no:  # already has a CV number
        return False
    if row.basvuru not in CV_TRIGGER_BASVURU_VALUES:
        return False
    return True


def find_candidates(rows: list[Row]) -> list[Row]:
    """Candidate rows, with duplicate postings removed.

    A row is skipped (no CV) when another row already covers the same posting (same
    İlan Numarası / job id, column M derived from K):
      - another row already has a CV No (column N) for that posting, OR
      - an earlier candidate row in this same scan already claimed it.
    So each distinct posting yields exactly one CV, even if the link is added twice.
    """
    done_keys = {_job_key(r.link) for r in rows if r.cv_no and r.link}
    candidates: list[Row] = []
    seen: set[str] = set()
    for r in rows:
        if not is_candidate(r):
            continue
        key = _job_key(r.link)
        if key and (key in done_keys or key in seen):
            logger.info(
                "Row %d skipped: same job already in the sheet (job id %s).",
                r.number, key,
            )
            continue
        seen.add(key)
        candidates.append(r)
    return candidates


def save_job_description(cv_no: int, job_description: str) -> Path:
    """İlan metnini job_description_<no>.md olarak kaydeder ve yolunu döndürür.

    cv-writer subagent'ı ilanı bu dosyadan okur; /cv-yenile ve mektup da sonradan aynı
    dosyayı kullanır (ilan LinkedIn'den kalksa bile).
    """
    settings.ensure_dirs()
    jd_path = settings.job_description_dir / f"job_description_{cv_no}.md"
    jd_path.write_text(job_description, encoding="utf-8")
    return jd_path


def save_cv_markdown(cv_no: int, cv_md: str) -> Path:
    """Analiz dosyasından çıkarılan temiz CV'yi cv_<no>.md olarak kaydeder."""
    settings.ensure_dirs()
    cv_path = settings.markdown_dir / f"cv_{cv_no}.md"
    cv_path.write_text(cv_md, encoding="utf-8")
    logger.info("Saved CV -> %s", cv_path)
    return cv_path


def _export_google_doc(cv_no: int, cv_md: str) -> None:
    """Build the .docx from the template, upload it to Drive as a Google Doc, and
    download that Doc back as a PDF into the local PDFs folder.

    The .docx is only an in-memory intermediary (Drive converts it to a Doc); no local
    .docx is kept. Best-effort: a failure here must not undo the Markdown CV that already
    succeeded. A single Drive client is reused so credentials load only once.
    """
    try:
        docx_bytes = docx_builder.build_docx(cv_md)
        client = drive_docs.DriveDocsClient()
        file_id = client.upload_as_google_doc(docx_bytes, f"cv_{cv_no}")
        pdf_bytes = client.export_as_pdf(file_id)
        (settings.pdf_dir / f"cv_{cv_no}.pdf").write_bytes(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Google Doc/PDF export failed for cv_%d (Markdown CV still saved).", cv_no)
        # The Markdown CV + sheet row still succeed, so this would otherwise be silent —
        # record it so a missing Google Doc/PDF is noticed.
        record_failure("drive_export", cv_no=cv_no, error=repr(exc))


def _scrape_fields(row: Row, scraper: Scraper, allow_staged: bool = False):
    """Scrape the job page once and return (JobPage, fields).

    `fields` are the only-empty column values to write to the sheet. Shared by the
    CV-generation path and the info-only (CV_GENERATION off) path.

    allow_staged: when the scrape fails and the panel staged this posting's text
    (state/pending_jd/<job_id>.md, written by /add-job), build a description-only JobPage
    from it instead of propagating the error — the CV is then grounded in exactly what
    the user read in the panel. City/work type/easy-apply stay empty, which is harmless:
    _fill_page_fields skips empty values, so the J/L written at append time survive.

    OFF by default, including on the CV path. Since the trigger moved to B == "Üretilecek"
    the user marks a row at application time, so a failed scrape most likely means the
    posting is gone — and a CV for a posting nobody can apply to is exactly the waste the
    deferred trigger exists to stop. prepare_job (mcp_server) writes EXPIRED_MARKER instead. Pass True
    (run_once.py --allow-staged) to force one out of the staged text anyway.
    """
    try:
        jp = scraper.fetch_job(row.link)
    except Exception as exc:  # noqa: BLE001 - RuntimeError (too short), ValueError, timeouts
        staged = (
            joblookup.load_pending_jd(joblookup.linkedin_job_id(row.link))
            if allow_staged
            else ""
        )
        if not staged:
            raise  # unchanged behaviour: the row is retried on the next scan
        logger.warning(
            "Scrape failed for row %d (%r); falling back to the %d-char description "
            "staged by the panel. City/work type stay empty.",
            row.number, exc, len(staged),
        )
        # Notify: this CV is grounded in the panel's heuristic text, not the posting page.
        record_failure("scrape_fallback", row=row.number, link=row.link, error=repr(exc))
        jp = JobPage(url=row.link, description=staged)
    else:
        logger.info(
            "Fetched page: %r @ %r | %s | %s (%d chars desc)",
            jp.title, jp.company, jp.city, jp.work_type, len(jp.description),
        )
    fields = {
        "C": jp.easy_apply,
        "F": jp.city,
        "H": jp.work_type,
        "L": jp.title,
        "J": jp.company,
        "J_url": jp.company_url,
    }
    return jp, fields


def _process_info_only(candidates: list[Row], sheets: SheetsClient) -> int:
    """CV-generation-OFF path: scrape each candidate's page for its info, write the
    only-empty fields (C/F/H/J/L) to the sheet, and mark N with NO_CV_MARKER so the row
    is handled once and never assigned a CV (even after the switch is turned back on).
    No Claude call, no Google Doc, no CV number consumed. Returns rows written.
    """
    count = 0
    with Scraper(headless=True) as scraper:
        for row in candidates:
            logger.info("Processing row %d (info-only, no CV) -> %s", row.number, row.link)
            try:
                # No allow_staged here, deliberately: this path wants the PAGE's fields,
                # and a staged JobPage carries none. Falling back would write a permanent
                # NO_CV_MARKER with zero information gained (and such a row is never
                # retro-generated). Retrying next scan is the better outcome. In practice
                # unreachable for panel-added rows anyway: with CV generation off,
                # /add-job writes the marker at append time, so they never become
                # candidates.
                _, fields = _scrape_fields(row, scraper)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Scrape failed for row %d; will retry next scan.", row.number
                )
                record_failure("scrape", row=row.number, link=row.link, error=repr(exc))
                continue
            try:
                sheets.write_info_only_row(row.number, fields, NO_CV_MARKER)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Sheet write failed for row %d (info-only); will retry next scan.",
                    row.number,
                )
                record_failure("sheet_write", row=row.number, link=row.link, error=repr(exc))
                continue
            count += 1
    return count


def select_candidates(
    rows: list[Row], only_row: int | None = None, limit: int | None = None
) -> list[Row]:
    """find_candidates + isteğe bağlı tek satır / adet sınırı (sheet sırasıyla)."""
    candidates = find_candidates(rows)
    if only_row is not None:
        candidates = [r for r in candidates if r.number == only_row]
        if not candidates:
            logger.warning(
                "Row %d is not a candidate (check: has link? CV No (N) empty? "
                "Başvuru (B) one of %s?).",
                only_row,
                sorted(CV_TRIGGER_BASVURU_VALUES),
            )
    if limit is not None:
        candidates = candidates[:limit]
    return candidates


def scan_candidates(
    only_row: int | None = None, limit: int | None = None
) -> tuple[SheetsClient, list[Row]]:
    """Sheet'i bir kez okuyup aday satırları döndürür. Model çağırmaz.

    Poller döngüsü bununla "iş var mı?" diye bakar; boşsa hiç agent başlatılmaz.
    """
    sheets = SheetsClient()
    # Satırı silinmiş ya da hiç üretilmemiş bekleyen ilan metinleri. Ucuz (klasörde
    # normalde 0-5 dosya olur) ve bunu yapabilecek tek uzun ömürlü süreç burası.
    joblookup.prune_pending_jd()
    rows = sheets.get_rows()
    return sheets, select_candidates(rows, only_row, limit)


def log_candidates(candidates: list[Row]) -> None:
    """Kuru çalıştırma (--dry-run) çıktısı: adayları listeler, hiçbir şey yazmaz."""
    if not candidates:
        logger.info("No candidate rows to process.")
        return
    logger.info("%d candidate row(s):", len(candidates))
    for r in candidates:
        logger.info("  [DRY] row %d | Başvuru=%r | %s", r.number, r.basvuru, r.link)
