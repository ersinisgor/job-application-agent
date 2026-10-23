"""Her Huntr board ilanının nasıl işleneceğini teşhis eder. Salt okuma (hiçbir şey değiştirmez).

ÖNEMLİ: önce çalışan poller'ı durdur (terminalinde Ctrl-C), çünkü aynı Chrome profilini
kullanıyor — bir profilde iki tarayıcı çakışır.

Board'daki her ilan için gösterir: ilan no'su (M sütunu), yeni görülüp görülmediği, zaten
sheet'te olup olmadığı ve ortaya çıkan karar (aktar / tekrar-uyarısı / zaten-işlendi).
Huntr'a eklediğin bir ilan CV'ye dönüşmediğinde işe yarar.

Kullanım:
    ./.venv/bin/python scripts/huntr_diagnose.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.applyjobs.config import settings  # noqa: E402
from src.applyjobs.huntr import HuntrClient  # noqa: E402
from src.applyjobs.pipeline import _job_key, load_huntr_seen  # noqa: E402
from src.applyjobs.reporting import setup_logging  # noqa: E402
from src.applyjobs.sheets import SheetsClient  # noqa: E402


def main() -> None:
    setup_logging()
    settings.validate()

    seen = load_huntr_seen()
    print(f"\nSEEN baseline: {'<none — next run will baseline>' if seen is None else f'{len(seen)} job key(s)'}")

    # Board JSON'u bazen tek seferde yüklenmiyor (ya da çalışan poller aynı Chrome profilini
    # kullanıyor) -> 0 ilan. Vazgeçmeden önce birkaç kez yeniden dene.
    jobs: list[dict] = []
    for attempt in range(1, 4):
        jobs = HuntrClient(headless=True).fetch_jobs()
        if jobs:
            break
        print(f"  (attempt {attempt}: board not loaded, retrying...)")
    print(f"Parsed {len(jobs)} job(s) from the board.")
    if not jobs:
        print(
            "\nBoard could not be read. Make sure the agent is fully STOPPED (Ctrl-C) so it\n"
            "is not using the same Chrome profile, then run this again."
        )
        return

    existing_by_key: dict[str, int] = {}
    for r in SheetsClient().get_rows():
        if r.link:
            existing_by_key.setdefault(_job_key(r.link), r.number)
    print(f"Sheet contains {len(existing_by_key)} job key(s).\n")

    seen_set = seen or set()
    print("--- per board job ---")
    for j in jobs:
        key = _job_key(j["url"])
        is_new = key not in seen_set
        in_sheet = key in existing_by_key
        if seen is None:
            decision = "BASELINE (first run: seen, no action)"
        elif not is_new:
            decision = "already handled (seen)"
        elif in_sheet:
            decision = f"DUPLICATE -> alert, no CV (sheet row {existing_by_key[key]})"
        else:
            decision = "IMPORT -> new row + CV"
        print(f"  {key:<18} new={is_new!s:<5} inSheet={in_sheet!s:<5} | {decision} | {(j.get('title') or '')[:32]}")


if __name__ == "__main__":
    main()
