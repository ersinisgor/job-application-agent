"""Find a job's sheet row, and read/stage its job description, by CV No or job id.

Shared by the CV poller (pipeline), the cover-letter feature (cover_letter,
summary_api) and the panel's "Ekle" button (summary_api -> /add-job).

IMPORTANT: this module must never import pipeline/scraper/huntr. Those pull in
Playwright at module scope, and summary_api imports this — the API process must
stay incapable of touching LinkedIn (see CLAUDE.md, "Do not automate the user's
LinkedIn session"). Only config + sheets belong here.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from .config import (
    PENDING_JD_DIR,
    PENDING_JD_MAX_AGE_DAYS,
    PENDING_JD_MIN_CHARS,
    settings,
)
from .sheets import Row, SheetsClient

logger = logging.getLogger("applyjobs.joblookup")

# LinkedIn job id inside a link, e.g. .../jobs/view/4427414076/... -> 4427414076.
# Deliberately duplicates pipeline._job_key's regex rather than importing it: that
# function returns a prefixed "li:<id>" key for the poller's de-duplication, and it
# lives behind the Playwright import chain. KEEP THE PATTERN IN SYNC with pipeline.py.
_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)")


def linkedin_job_id(link: str) -> str:
    """Bare LinkedIn job id from a sheet link, e.g. "4427414076". "" if not LinkedIn.

    Bare (no "li:" prefix) so it matches what the extension's getCurrentJobId()
    sends, with no translation at the API boundary.
    """
    if not link:
        return ""
    m = _LINKEDIN_ID_RE.search(link)
    return m.group(1) if m else ""


def find_row_for_cv_no(rows: list[Row], cv_no: int) -> Row | None:
    """The row whose CV No (column N) is exactly cv_no. None if absent."""
    for r in rows:
        if SheetsClient._as_int(r.cv_no) == cv_no:
            return r
    return None


def targets_in_range(rows: list[Row], start: int, end: int) -> list[tuple[int, Row]]:
    """(cv_no, row) pairs whose numeric CV No is in [start, end], sorted by cv_no."""
    targets = [
        (n, r)
        for r in rows
        if (n := SheetsClient._as_int(r.cv_no)) is not None and start <= n <= end
    ]
    targets.sort(key=lambda t: t[0])
    return targets


def build_job_index(rows: list[Row]) -> dict[str, int]:
    """Bare LinkedIn job id -> CV No, for every row with a link and a numeric N."""
    index: dict[str, int] = {}
    for r in rows:
        job_id = linkedin_job_id(r.link)
        n = SheetsClient._as_int(r.cv_no)
        if job_id and n is not None:
            index[job_id] = n
    return index


def build_link_index(rows: list[Row]) -> dict[str, Row]:
    """Bare LinkedIn job id -> the FIRST row carrying that link, CV No or not.

    build_job_index() only sees rows that already have a numeric N, so it cannot answer
    "is this posting already in the sheet, still waiting for its CV?" — which is exactly
    the duplicate check /add-job needs. First row wins, like sync_huntr_to_sheet.
    """
    index: dict[str, Row] = {}
    for r in rows:
        job_id = linkedin_job_id(r.link)
        if job_id:
            index.setdefault(job_id, r)
    return index


def load_saved_jd(cv_no: int) -> str:
    """The job description stored when the CV was first made, stripped.

    Re-using it is what makes regeneration and on-demand cover letters robust against
    expired/removed LinkedIn postings.
    """
    jd_path = settings.job_description_dir / f"job_description_{cv_no}.md"
    if not jd_path.exists():
        raise FileNotFoundError(f"Saved job description not found: {jd_path}")
    job_description = jd_path.read_text(encoding="utf-8").strip()
    if not job_description:
        raise ValueError(f"Saved job description is empty: {jd_path}")
    return job_description


# --- Descriptions staged by the panel's "Ekle" button ----------------------------
# The panel already reads the posting to summarize it, so /add-job stages that text next
# to the new row. The poller's guest-view scrape stays the PRIMARY source; the staged
# copy is only read when that scrape fails, and is deleted once the CV exists (from then
# on job_description_<no>.md is the record regenerate/cover-letter use).


def pending_jd_path(job_id: str) -> Path:
    """state/pending_jd/<job_id>.md for a bare LinkedIn job id.

    Rejects anything non-numeric: job_id arrives over HTTP from the extension, so this
    is the path-traversal guard as much as a sanity check.
    """
    if not job_id or not job_id.isdigit():
        raise ValueError(f"Not a LinkedIn job id: {job_id!r}")
    return PENDING_JD_DIR / f"{job_id}.md"


def save_pending_jd(job_id: str, text: str) -> bool:
    """Stage the panel's posting text. False (and nothing written) if it is too short.

    Atomic (tmp + replace) so the poller can never read a half-written file.
    """
    text = (text or "").strip()
    if len(text) < PENDING_JD_MIN_CHARS:
        return False
    path = pending_jd_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


def load_pending_jd(job_id: str) -> str:
    """The staged text, or "" when absent/too short/unreadable.

    Never raises: this is a fallback, so it must not turn a scrape failure into a
    different failure.
    """
    try:
        text = pending_jd_path(job_id).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""
    return text if len(text) >= PENDING_JD_MIN_CHARS else ""


def clear_pending_jd(job_id: str) -> None:
    """Drop the staged text once its CV has been written."""
    try:
        pending_jd_path(job_id).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def prune_pending_jd(max_age_days: int = PENDING_JD_MAX_AGE_DAYS) -> int:
    """Delete staged files older than max_age_days; return how many were removed."""
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        entries = list(PENDING_JD_DIR.glob("*.md"))
    except OSError:
        return 0
    for path in entries:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("Pruned %d stale staged job description(s).", removed)
    return removed
