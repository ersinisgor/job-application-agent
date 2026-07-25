"""Find a job's sheet row and saved job description by CV No or LinkedIn job id.

Shared by the CV poller (pipeline) and the cover-letter feature (cover_letter,
summary_api).

IMPORTANT: this module must never import pipeline/scraper/huntr. Those pull in
Playwright at module scope, and summary_api imports this — the API process must
stay incapable of touching LinkedIn (see CLAUDE.md, "Do not automate the user's
LinkedIn session"). Only config + sheets belong here.
"""
from __future__ import annotations

import re

from .config import settings
from .sheets import Row, SheetsClient

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
