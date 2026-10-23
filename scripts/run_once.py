"""Sheet'i bir kez tarar ve aday satırlar için CV agent'ını çalıştırır (cron / elle test).

Aday satır: linki olan, CV No'su (N) boş ve Başvuru (B) sütunu "Üretilecek" olan satır.
Başvuracağın satırları işaretle, sonra bunu çalıştır (ya da scripts/cv_uret.command'a çift
tıkla). CV'yi Claude Code agent'ı üretir: `claude -p "/cv-uret ..."` (agent_runner).

Kullanım:
    python scripts/run_once.py             # tüm aday satırları bir kez işle
    python scripts/run_once.py --dry-run   # sadece adayları listele, hiçbir şey yazma (model yok)
    python scripts/run_once.py --limit 1   # en fazla 1 aday işle (ilk test için iyi)
    python scripts/run_once.py --row 430   # sadece sheet satırı 430
    python scripts/run_once.py --row 430 --allow-staged   # ilan kalkmış: panelin metnini kullan
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.applyjobs import agent_runner  # noqa: E402
from src.applyjobs.config import settings  # noqa: E402
from src.applyjobs.pipeline import (  # noqa: E402
    _process_info_only,
    log_candidates,
    scan_candidates,
    sync_huntr_to_sheet,
)
from src.applyjobs.reporting import setup_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one scan of the job sheet.")
    parser.add_argument("--dry-run", action="store_true", help="List candidates only.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N candidates.")
    parser.add_argument("--row", type=int, default=None, help="Process only this sheet row number.")
    parser.add_argument(
        "--huntr", action="store_true", help="Sync new Huntr jobs into the sheet first."
    )
    parser.add_argument(
        "--allow-staged",
        action="store_true",
        help=(
            "When the posting can no longer be fetched, generate from the description the "
            "panel staged at 'Ekle' time instead of marking the row 'Kalkmış'."
        ),
    )
    args = parser.parse_args()

    setup_logging()

    settings.validate()
    settings.ensure_dirs()
    log = logging.getLogger("applyjobs")
    if args.huntr:
        imported = sync_huntr_to_sheet()
        log.info("Huntr: %d new job(s) imported.", imported)

    # Önce Python'da (ücretsiz) aday var mı diye bak: yoksa agent hiç başlatılmaz.
    sheets, candidates = scan_candidates(only_row=args.row, limit=args.limit)
    if args.dry_run or not candidates:
        log_candidates(candidates)
        return

    if not settings.cv_generation:
        # CV üretimi kapalı (info-only): model yok, sadece sayfa bilgisi + "Yok" işaretçisi.
        count = _process_info_only(candidates, sheets)
        log.info("Done. Saved %d row(s) (info-only, no CV).", count)
        return

    log.info("%d candidate row(s); starting the CV agent (/cv-uret).", len(candidates))
    try:
        result = agent_runner.run_cv_batch(
            only_row=args.row, limit=args.limit, allow_staged=args.allow_staged
        )
    except agent_runner.AgentBusy as exc:
        log.warning("%s Bitince tekrar dene.", exc)
        raise SystemExit(2)
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
