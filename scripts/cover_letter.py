"""Daha önce üretilmiş bir CV için, istendiğinde mektup üretir.

Her başvuru mektup istemez; bu yüzden mektuplar her CV'nin yanında değil, tek tek üretilir.
İlanın KAYDEDİLMİŞ CV'si + ilan metninden kurulur; ilan kalktıktan çok sonra da çalışır.
Mektubu cover-letter-writer agent'ı yazar (`claude -p "/mektup ..."`).

Bir mektup (CV No, dil) başına tam bir kez üretilir: yeniden çalıştırmak kaydedileni modeli
çağırmadan yazdırır. Üzerine yazmak için --force kullan.

Kullanım:
    python scripts/cover_letter.py --cv-no 305
    python scripts/cover_letter.py --cv-no 305 --lang tr
    python scripts/cover_letter.py --cv-no 305 --force      # yeniden üret, üzerine yaz
    python scripts/cover_letter.py --cv-no 305 --no-copy    # panoya dokunma
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
    """Mektubu macOS panosuna koyar. Best-effort — çalışmayı asla başarısız yapmaz."""
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
