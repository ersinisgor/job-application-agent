"""Var olan CV'lerin bir aralığını (CV No'ya göre) güncel ayarlarla yeniden üretir.

Aynı CV numaraları korunur; cv_<no>.md / _analysis / _review üzerine yazılır, aynı adlı
Google Doc güncellenir, PDF'i yeniden indirilir ve Match Rate (P) sütunu yenilenir. Diğer
sheet sütunlarına dokunulmaz. İşi Claude Code agent'ı yapar: `claude -p "/cv-yenile ..."`.

Kullanım:
    python scripts/regenerate.py --from 200 --to 219
    python scripts/regenerate.py --from 200 --to 219 --dry-run

Sadece bu çalışma için daha güçlü bir model/effort kullanmak istersen ortam değişkenini
komutun önüne yaz:
    CV_MODEL=claude-opus-5-5 CV_EFFORT=high \
        ./.venv/bin/python scripts/regenerate.py --from 200 --to 219

Yeniden üretimi serbest metinli bir notla yönlendirmek için --instruction / -i ekle (notu
aralıktaki HER CV'ye yüksek öncelikli yönerge olarak uygular; dürüstlük sözleşmesi yine
geçerlidir):
    ./.venv/bin/python scripts/regenerate.py --from 309 --to 309 \
        -i "Remove the Library Management System project and feature a .NET project instead"
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.applyjobs import agent_runner, joblookup  # noqa: E402
from src.applyjobs.config import settings  # noqa: E402
from src.applyjobs.reporting import setup_logging  # noqa: E402
from src.applyjobs.sheets import SheetsClient  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-generate a range of existing CVs.")
    parser.add_argument("--from", dest="start", type=int, required=True, help="First CV No.")
    parser.add_argument("--to", dest="end", type=int, required=True, help="Last CV No (inclusive).")
    parser.add_argument("--dry-run", action="store_true", help="List target CVs only.")
    parser.add_argument(
        "--instruction",
        "-i",
        default="",
        help=(
            "Free-text override applied to every CV in the range as a high-priority "
            'directive, e.g. -i "Drop project X and feature a .NET project instead". '
            "Still bound by the honesty contract (no fabricated projects/skills)."
        ),
    )
    args = parser.parse_args()

    setup_logging()

    settings.validate()
    settings.ensure_dirs()
    log = logging.getLogger("applyjobs")

    targets = joblookup.targets_in_range(SheetsClient().get_rows(), args.start, args.end)
    if not targets:
        log.info("No rows with CV No in [%d, %d].", args.start, args.end)
        return
    log.info(
        "Regenerating %d CV(s) [%s] with model=%s effort=%s (review=%s).",
        len(targets),
        ", ".join(str(n) for n, _ in targets),
        settings.cv_model,
        settings.cv_effort,
        settings.cv_review,
    )
    if args.instruction.strip():
        log.info("Applying per-run override instruction to each CV: %s", args.instruction.strip())
    if args.dry_run:
        for n, r in targets:
            log.info("  [DRY] CV %d -> sheet row %d", n, r.number)
        return

    try:
        result = agent_runner.run_regenerate(args.start, args.end, args.instruction)
    except agent_runner.AgentBusy as exc:
        log.warning("%s Bitince tekrar dene.", exc)
        raise SystemExit(2)
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
