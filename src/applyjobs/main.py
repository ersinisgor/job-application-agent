"""Giriş noktası (loop): sheet'i sürekli yoklar, iş varsa CV agent'ını başlatır.

Her turda Python, sheet'i okuyup aday satır (link + boş N + B == "Üretilecek") var mı diye
bakar; bu adımda model çağrılmaz. Aday varsa `claude -p "/cv-uret"` (agent_runner) bir
kez başlatılır ve bütün adayları sırayla işler. Boş turlar hiçbir kota harcamaz.
"""
from __future__ import annotations

import logging
import time

from . import agent_runner
from .config import settings
from .pipeline import _job_key, _process_info_only, scan_candidates, sync_huntr_to_sheet
from .reporting import LOG_FILE, FAILURES_FILE, setup_logging

# Agent bir satırı bitiremediyse (üretim hatası, sheet yazılamadı...) satır aday kalır.
# Eski hat her turda (20 sn) yeniden denerdi; bir agent çalışması dakikalar ve kota
# harcadığı için aynı satır bu kadar süre boyunca tekrar denenmez.
RETRY_COOLDOWN_SECONDS = 15 * 60


def main() -> None:
    setup_logging()
    log = logging.getLogger("applyjobs")
    log.info("Logs: %s | failures: %s", LOG_FILE, FAILURES_FILE)

    settings.validate()
    settings.ensure_dirs()

    huntr_enabled = bool(settings.huntr_board_url)
    log.info(
        "Job Application Agent started. Polling every %ds | CV agent model=%s effort=%s | "
        "CV generation=%s | Huntr=%s | output=%s",
        settings.poll_interval,
        settings.cv_model,
        settings.cv_effort,
        "on" if settings.cv_generation else "OFF (info-only: import + save fields, no CV)",
        f"on (every {settings.huntr_poll_interval}s)" if huntr_enabled else "off",
        settings.output_dir,
    )

    interval = settings.huntr_poll_interval if huntr_enabled else settings.poll_interval
    last_attempt: dict[str, float] = {}  # ilan anahtarı → son agent denemesi (monotonic)
    while True:
        try:
            if huntr_enabled:
                try:
                    imported = sync_huntr_to_sheet()
                    if imported:
                        log.info("Huntr: %d new job(s) imported into the sheet.", imported)
                except Exception:  # noqa: BLE001
                    log.exception("Huntr sync failed; continuing with sheet scan.")

            sheets, candidates = scan_candidates()
            if candidates and not settings.cv_generation:
                processed = _process_info_only(candidates, sheets)
                if processed:
                    log.info("Scan complete: %d row(s) saved (info-only, no CV).", processed)
            elif candidates:
                now = time.monotonic()
                fresh = [
                    r for r in candidates
                    if now - last_attempt.get(_job_key(r.link), -RETRY_COOLDOWN_SECONDS)
                    >= RETRY_COOLDOWN_SECONDS
                ]
                if fresh:
                    for r in candidates:
                        last_attempt[_job_key(r.link)] = now
                    log.info("%d candidate row(s); starting the CV agent.", len(candidates))
                    try:
                        agent_runner.run_cv_batch()
                    except agent_runner.AgentBusy as exc:
                        # cv_uret.command şu an çalışıyor; o bitirince satırlar zaten kapanır.
                        log.info("%s Skipping this round.", exc)
        except KeyboardInterrupt:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Scan failed; will retry next interval.")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            break

    log.info("Stopped.")


if __name__ == "__main__":
    main()
