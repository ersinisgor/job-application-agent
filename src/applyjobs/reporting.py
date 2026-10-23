"""Sorunları, izlemediğin bir terminalde kayıp gitmek yerine sonradan görünür kılar.

Üç katman:
  1. setup_logging() — konsol + tam ayrıntılı döner bir log dosyası (state/agent.log)
     (traceback'ler dahil); hiçbir şey kaybolmaz.
  2. record_failure() — her hata için state/failures.log'a insanın okuyabileceği TEK bir
     satır ekler. Bir çalışmadan sonra göz atılacak kısa "rapor" budur.
  3. Her hatada best-effort bir macOS masaüstü bildirimi; terminali izlemeden haberin olur.
"""
from __future__ import annotations

import datetime
import logging
import subprocess
import sys
from logging.handlers import RotatingFileHandler

from .config import STATE_DIR

LOG_FILE = STATE_DIR / "agent.log"
FAILURES_FILE = STATE_DIR / "failures.log"

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_console_logging(level: int = logging.INFO) -> None:
    """Yalnızca konsola loglama; özet API'si süreci için. İki kez çağırmak güvenli.

    Bilerek setup_logging() DEĞİL: o, state/agent.log'a bir RotatingFileHandler da bağlar ve o
    dosyanın sahibi poller. Aynı dosyayı döndüren iki süreç yarışır ve birbirinin çıktısını
    keser. API poller ile aynı terminalde çalışır (scripts/start.sh), yani satırlarının yeri
    stdout — o olmadan uygulama düzeyindeki bir log satırı ("Ekle" hangi satıra yazdı, bir mektup
    neden 404 verdi) hiçbir yere gitmez ve yalnızca uvicorn'un erişim satırı görünür.
    """
    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(h, "_applyjobs_console", False) for h in root.handlers):
        return
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATEFMT))
    console._applyjobs_console = True  # işaret: ikinci bir çağrı etkisiz kalsın
    root.addHandler(console)


def setup_logging(level: int = logging.INFO) -> None:
    """Konsol + döner dosya loglamasını kurar. Program başlangıcında bir kez çağırmak güvenli."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # failures.log'u her zaman (boş) oluştur ki yeri kolay bulunsun; boş bir dosya sadece
    # "henüz hata yok" demektir.
    FAILURES_FILE.touch(exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return  # already configured (don't add duplicate handlers)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def _notify(title: str, message: str) -> None:
    """Best-effort macOS masaüstü bildirimi; başka yerde ya da herhangi bir hatada etkisiz."""
    if sys.platform != "darwin":
        return
    try:
        safe = message.replace('"', "'")[:200]
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe}" with title "{title}"'],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        pass


def record_failure(
    stage: str,
    *,
    row: int | None = None,
    cv_no: int | None = None,
    link: str = "",
    error: str = "",
) -> None:
    """Bir hatayı kaydeder: state/failures.log'a ekler, loglar ve bildirim gösterir.

    stage örnekleri: "generate", "drive_export", "sheet_write", "regenerate", "agent_run".
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    one_line_error = " ".join(str(error).split())[:300]
    line = f"{ts} | {stage:<12} | row={row} cv_no={cv_no} | {link} | {one_line_error}\n"
    try:
        with FAILURES_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        logger.exception("Could not write to %s", FAILURES_FILE)
    logger.error("FAILURE [%s] row=%s cv_no=%s: %s", stage, row, cv_no, one_line_error)
    _notify("job-apply-agent — hata", f"{stage}: row={row} cv_no={cv_no}")


def record_duplicate(link: str, job_key: str, sheet_row: int | None = None) -> None:
    """Huntr'a yeni eklenen bir ilan zaten sheet'te; bu yüzden onun için CV üretilmez.

    Bir hata gibi yüzeye çıkarılır (masaüstü bildirimi + failures.log'da bir satır) ki
    kullanıcı CV yapıldı sanmak yerine fark etsin.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    job_id = job_key.split(":", 1)[-1]  # "li:4364788282" -> "4364788282"
    where = f"satır {sheet_row}" if sheet_row else "mevcut bir satır"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | DUPLICATE    | İlan no {job_id} zaten sheet'te ({where}) | {link} | CV ÜRETİLMEDİ\n"
    try:
        with FAILURES_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        logger.exception("Could not write to %s", FAILURES_FILE)
    logger.warning(
        "DUPLICATE: job %s already in the sheet (%s) — no CV generated.", job_id, where
    )
    _notify(
        "job-apply-agent — tekrar ilan",
        f"İlan no {job_id} zaten sheet'te ({where}); CV üretilmedi.",
    )
