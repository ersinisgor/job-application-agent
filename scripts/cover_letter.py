"""Produce the cover letter for one already-generated CV, on demand.

Only some applications ask for a cover letter, so letters are made one at a time
instead of alongside every CV. Built from the job's SAVED CV + job description, so it
works long after the posting is gone.

A letter is generated exactly once per (CV No, language): re-running prints the saved
one without calling the model. Use --force to overwrite it.

Usage:
    python scripts/cover_letter.py --cv-no 305
    python scripts/cover_letter.py --cv-no 305 --lang tr
    python scripts/cover_letter.py --cv-no 305 --force      # regenerate, overwrite
    python scripts/cover_letter.py --cv-no 305 --no-copy    # don't touch the clipboard
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.applyjobs import cover_letter  # noqa: E402
from src.applyjobs.config import settings  # noqa: E402
from src.applyjobs.reporting import setup_logging  # noqa: E402


def _copy(text: str) -> bool:
    """Put the letter on the macOS clipboard. Best-effort — never fails the run."""
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a cover letter for one CV.")
    parser.add_argument("--cv-no", type=int, required=True, help="CV No (sheet column N).")
    parser.add_argument(
        "--lang",
        default="en",
        choices=sorted(cover_letter.LANGS),
        help="Letter language (default: en).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if the letter already exists (overwrites it).",
    )
    parser.add_argument("--no-copy", action="store_true", help="Don't copy to the clipboard.")
    args = parser.parse_args()

    setup_logging()
    settings.validate()
    settings.ensure_dirs()
    log = logging.getLogger("applyjobs")

    try:
        text, created = cover_letter.get_or_create(
            args.cv_no, lang=args.lang, force=args.force
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        raise SystemExit(1)

    path = cover_letter.cover_letter_path(args.cv_no, args.lang)
    origin = "üretildi" if created else "cache'ten okundu (model çağrısı yok)"
    print(f"\n{text}\n")
    print(f"CV {args.cv_no} | {args.lang} | {origin}")
    print(f"Dosya: {path}")
    if not args.no_copy:
        print("Panoya kopyalandı." if _copy(text) else "Panoya kopyalanamadı (pbcopy yok?).")


if __name__ == "__main__":
    main()
