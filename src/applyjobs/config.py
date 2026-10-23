"""Central configuration: loads .env and resolves project paths.

All other modules import `settings` from here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = two levels up from this file (src/applyjobs/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

# The candidate's facts (CV + projects): the single source of truth every agent reads.
PROFILE_DIR = PROJECT_ROOT / "profile"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
STATE_DIR = PROJECT_ROOT / "state"
# Generated CVs, analyses, job descriptions and cover letters (gitignored).
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Config asset files
CV_BASE_FILE = PROFILE_DIR / "cv_base.md"
PROJECTS_LIST_FILE = PROFILE_DIR / "projects.md"

# Config asset: the .docx template for the Google Docs output
CV_TEMPLATE_FILE = TEMPLATES_DIR / "cv_template.docx"

# Credential files
SERVICE_ACCOUNT_FILE = CREDENTIALS_DIR / "service_account.json"
LINKEDIN_STATE_FILE = CREDENTIALS_DIR / "linkedin_state.json"
# Huntr login is Google-SSO gated, which blocks automated browsers. We therefore use
# a persistent real-Chrome profile (not a storage_state file) so the session sticks
# and Google's "browser not secure" block is avoided.
HUNTR_PROFILE_DIR = CREDENTIALS_DIR / "huntr_profile"
# OAuth (user) credentials for creating Google Docs in Drive
OAUTH_CLIENT_FILE = CREDENTIALS_DIR / "oauth_client.json"
OAUTH_TOKEN_FILE = CREDENTIALS_DIR / "oauth_token.json"

# State
PROCESSED_STATE_FILE = STATE_DIR / "processed.json"
# Huntr board job keys we've already processed (baseline + handled). Replaces the old
# createdAt cursor, which was unreliable (createdAt isn't always the save time).
HUNTR_SEEN_FILE = STATE_DIR / "huntr_seen.json"
# Legacy: highest Huntr job createdAt (no longer used; kept so old files are harmless).
HUNTR_CURSOR_FILE = STATE_DIR / "huntr_cursor.txt"
# Job-summary cache for the browser-extension API, keyed by LinkedIn job id, so a
# posting is summarized once and survives an API restart.
SUMMARY_CACHE_FILE = STATE_DIR / "summary_cache.json"

# Job descriptions staged by the extension panel's "Ekle" button, keyed by LinkedIn job
# id. The poller's guest-view scrape stays PRIMARY; this text is only read when that
# scrape fails, so a CV is still produced from what the user actually saw in the panel.
PENDING_JD_DIR = STATE_DIR / "pending_jd"
# Below this many characters the staged text is not a posting (a half-loaded stub), and
# a CV grounded in it would be worse than none. Deliberately above scraper's 80-char floor.
PENDING_JD_MIN_CHARS = 200
# Staged files are deleted once their CV is written; anything older than this is junk
# (row deleted by hand, CV generation off, an append that failed).
PENDING_JD_MAX_AGE_DAYS = 14

# Advisory lock guarding a whole download -> edit -> upload of the .xlsx. Two processes
# now write it: the CV poller and the summary API (the panel's "Ekle" button).
SHEET_LOCK_FILE = STATE_DIR / "sheet.lock"

# Values in the "Başvuru" (B) column that DO trigger CV generation. An allow-list on
# purpose: a row is added to the sheet the moment the posting looks interesting, but the
# application often happens days later, by which time the posting may be gone — so a CV
# made at add time is frequently a CV for a job never applied to. The user marks the row
# "Üretilecek" when actually applying, and only then is a CV made. Keep this in sync with
# sheets.DROPDOWNS["B"], which is what the sheet's dropdown actually offers.
CV_TRIGGER_BASVURU_VALUES = {"Üretilecek"}

# Marker written to the CV No column (N) for rows imported while CV generation is OFF.
# It is non-numeric, so it is ignored by CV numbering yet still counts as "done" — the
# row keeps its scraped info but is never (re-)assigned a CV. Clear it manually to make
# the row eligible for a CV again.
NO_CV_MARKER = "Yok"

# Marker written to N when a marked row's posting can no longer be fetched. No CV is made
# and no CV number is consumed: the whole point of the deferred trigger is to not spend a
# generation on a posting that is gone. Clear N and re-mark B to try again (a scrape can
# also fail for LinkedIn-side reasons), or force one from the panel's staged text with
# `run_once.py --row N --allow-staged`.
EXPIRED_MARKER = "Kalkmış"


def _expand(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str)).resolve()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "on", "yes", "evet", "açık")


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    # CV agent'larının (cv-writer / cv-reviewer) modeli ve effort'u. claude -p'ye
    # --model / --effort olarak geçer. Eski CLAUDE_MODEL / CLAUDE_EFFORT yerine yeni ad:
    # Claude Code kendi CLAUDE_EFFORT değişkenini her Bash komutuna ihraç ediyor ve
    # load_dotenv var olanı ezmediği için .env'deki değer sessizce yok sayılıyordu.
    cv_model: str
    cv_effort: str
    # claude CLI'nin yolu. Boşsa PATH'te, sonra ~/.local/bin/claude'da aranır (Finder'dan
    # çift tıklanan .command dosyalarında PATH dar olur).
    claude_bin: str
    # Model used by the LinkedIn Job Summary API (separate from claude_model, which
    # is used for CV generation). Defaults to Haiku for fast, low-cost summaries.
    summary_model: str
    # Model used for on-demand cover letters (separate again: the letter is short
    # prose, so it needs neither the CV's thinking budget nor the summary's Haiku).
    cover_letter_model: str
    cv_review: bool
    cv_generation: bool
    spreadsheet_id: str
    sheet_name: str
    poll_interval: int
    output_dir: Path
    analysis_dir: Path
    job_description_dir: Path
    cover_letter_dir: Path
    resumes_folder_name: str
    resumes_folder_id: str
    huntr_board_url: str
    huntr_poll_interval: int

    @classmethod
    def load(cls) -> "Settings":
        # Every generated file lives inside the project, under outputs/ (gitignored).
        default_output = str(OUTPUTS_DIR / "cv")
        default_analysis = str(OUTPUTS_DIR / "cv" / "analysis")
        default_jd = str(OUTPUTS_DIR / "job_descriptions")
        # Shares a folder with the hand-made legacy letters (cover_letter_<no>_<be|fs>.docx,
        # up to No. 138). New files are cover_letter_<no>_<lang>.md — different suffix and
        # extension, so they coexist. Never glob this directory to find a letter.
        default_cover = str(OUTPUTS_DIR / "cover_letters")
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            cv_model=os.getenv("CV_MODEL", "claude-sonnet-5"),
            # low / medium / high / xhigh / max. medium, ölçülmüş en iyi denge (bkz. KULLANIM.md).
            cv_effort=os.getenv("CV_EFFORT", "medium").strip().lower(),
            claude_bin=os.getenv("CLAUDE_BIN", "").strip(),
            # Model for the LinkedIn Job Summary API (extension). Haiku by default.
            summary_model=os.getenv("SUMMARY_MODEL", "claude-haiku-4-5"),
            # Mektuplar: cover-letter-writer agent'ı bu modelle, düşük effort ile çalışır.
            cover_letter_model=os.getenv("COVER_LETTER_MODEL", "claude-sonnet-5"),
            # Second expert QA pass on each CV (OFF by default: the verify/fix
            # checklist is folded into the single generation prompt, STEP 12).
            cv_review=_env_bool("CV_REVIEW", False),
            # Master switch for CV generation. ON (default): new jobs get a full CV +
            # sheet info. OFF: new jobs are still imported and their page info is written
            # to the sheet, but NO CV is produced (column N gets the marker "Yok" so the
            # row is not retro-generated when the switch is turned back on).
            cv_generation=_env_bool("CV_GENERATION", True),
            spreadsheet_id=os.getenv("SPREADSHEET_ID", ""),
            sheet_name=os.getenv("SHEET_NAME", "Sayfa1"),
            poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
            output_dir=_expand(os.getenv("OUTPUT_DIR", default_output)),
            analysis_dir=_expand(os.getenv("ANALYSIS_DIR", default_analysis)),
            job_description_dir=_expand(os.getenv("JOB_DESCRIPTION_DIR", default_jd)),
            cover_letter_dir=_expand(os.getenv("COVER_LETTER_DIR", default_cover)),
            resumes_folder_name=os.getenv("RESUMES_FOLDER_NAME", "Resumes Based on Jobs"),
            resumes_folder_id=os.getenv("RESUMES_FOLDER_ID", ""),
            # Huntr is OFF unless a board URL is provided (feature flag).
            huntr_board_url=os.getenv("HUNTR_BOARD_URL", ""),
            huntr_poll_interval=int(os.getenv("HUNTR_POLL_INTERVAL", "30")),
        )

    @property
    def markdown_dir(self) -> Path:
        """Where the Markdown CVs live (subfolder of the CVs output dir)."""
        return self.output_dir / "markdown"

    @property
    def pdf_dir(self) -> Path:
        """Where the CV PDFs (exported from the Google Docs) are downloaded."""
        return self.output_dir / "pdf"

    def validate(self) -> None:
        # ANTHROPIC_API_KEY burada aranmıyor: CV ve mektup artık Claude Code agent'larıyla
        # (abonelik girişiyle) üretiliyor. Anahtar sadece panel özeti için summary_api'de lazım.
        missing = []
        if not self.spreadsheet_id:
            missing.append("SPREADSHEET_ID")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )
        if not SERVICE_ACCOUNT_FILE.exists():
            raise RuntimeError(
                f"Service account key not found at {SERVICE_ACCOUNT_FILE}. "
                f"Create one in Google Cloud and share the sheet with its email."
            )

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.job_description_dir.mkdir(parents=True, exist_ok=True)
        self.cover_letter_dir.mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_JD_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings.load()
