"""Kullanıcının Huntr board'unu Playwright ile okur.

Huntr bireysel hesaplar için herkese açık bir API sunmuyor; bu yüzden girişli web
uygulamasını (huntr.co) sürer, board'un arka planda yüklediği JSON'u yakalar ve ilan
kayıtlarını sezgisel olarak çıkarırız. Böylece kırılgan DOM seçicilerine bağımlı kalmayız.

Kurulum: oturumu kaydetmek için `scripts/huntr_login.py`'yi bir kez çalıştır. Ayrıştırma bir
gün ilan kaçırırsa, alan eşlemesi canlı board'a göre iyileştirilebilsin diye sayfayı +
yakalanan JSON'u dökmek için `scripts/huntr_debug.py`'yi çalıştır.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from .config import HUNTR_PROFILE_DIR, settings
from .scraper import _USER_AGENT, _clean_html_to_text

logger = logging.getLogger(__name__)


def launch_huntr_context(pw, headless: bool):
    """Huntr için kalıcı, gerçek bir Chrome bağlamı açar.

    Sistem Chrome'unu (channel="chrome") kullanır ve Google'ın "bu tarayıcı güvenli olmayabilir"
    deyip girişi engellemesine yol açan otomasyon bayraklarını kaldırır. Oturum
    HUNTR_PROFILE_DIR'de kalır, yani giriş yalnızca bir kez gerekir.
    """
    HUNTR_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # Önceki çökmüş/temizlenmemiş bir çalışmadan kalan bayat Chrome kilit dosyalarını sil; yoksa
    # "profile already in use" hatası verir. Tek ve sıralı kullanımımız için güvenli.
    for lock in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (HUNTR_PROFILE_DIR / lock).unlink()
        except (FileNotFoundError, OSError):
            pass
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(HUNTR_PROFILE_DIR),
        headless=headless,
        channel="chrome",
        user_agent=_USER_AGENT,
        # Otomasyon/no-sandbox bayraklarını kaldır ki Chrome normal bir tarayıcı gibi davransın
        # (bilgi çubuğu yok ve Google'ın "tarayıcı güvenli değil" giriş engeli aşılır).
        ignore_default_args=["--enable-automation", "--no-sandbox"],
        args=["--disable-blink-features=AutomationControlled"],
    )

def _values(x):
    """Huntr ships these collections as {id: obj} dicts (sometimes lists)."""
    if isinstance(x, dict):
        return list(x.values())
    if isinstance(x, list):
        return x
    return []


def _find_board_payload(payloads: list) -> dict | None:
    """Board yükü, hem 'jobs' hem 'companies' taşıyan JSON nesnesidir."""
    for p in payloads:
        if isinstance(p, dict) and "jobs" in p and "companies" in p:
            return p
    return None


def _normalize_url(url: str) -> str:
    """Bir LinkedIn arama URL'sini (…currentJobId=ID…) temiz bir /jobs/view/ID/'ye çevirir."""
    url = (url or "").strip()
    if "linkedin.com" in url and "currentJobId=" in url:
        m = re.search(r"currentJobId=(\d+)", url)
        if m:
            return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    return url


def _simplify_location(loc: str) -> str:
    """Huntr'ın (bazen coğrafi kodlanmış) adresini kısa, şehir benzeri bir değere indirir.

    'Istanbul, Turkey' -> 'Istanbul'; 'Remote' -> 'Remote'. Yalnızca sayısal ya da posta kodu
    parçalarını atar ve ilk anlamlı kısmı tutar.
    """
    loc = (loc or "").strip()
    if not loc:
        return ""
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    parts = [
        p for p in parts
        if not re.fullmatch(r"[\d\s\-]+", p)  # "11", "10111"
        and not re.fullmatch(r"[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d", p)  # posta kodu "R2K 3A5"
    ]
    return parts[0] if parts else loc.split(",")[0].strip()


def parse_board(payload: dict) -> list[dict]:
    """Huntr ilanlarını şirketlerle {company,title,location,url,description} olarak birleştirir."""
    comp_name = {}
    for c in _values(payload.get("companies")):
        cid = c.get("_id") or c.get("id")
        if cid:
            comp_name[cid] = (c.get("name") or "").strip()

    jobs: list[dict] = []
    for j in _values(payload.get("jobs")):
        url = _normalize_url(j.get("url", ""))
        if not url:
            continue
        loc = j.get("location")
        location = loc.get("address", "") if isinstance(loc, dict) else (loc or "")
        jobs.append(
            {
                "company": comp_name.get(j.get("_company"), ""),
                "title": (j.get("title") or "").strip(),
                "location": _simplify_location(location),
                "url": url,
                "description": _clean_html_to_text(j.get("htmlDescription", "")),
                "created_at": (j.get("createdAt") or "").strip(),
            }
        )
    return jobs


class HuntrClient:
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless

    def _capture_payloads(self, context) -> list:
        """Board'u yükler ve yükleme sırasında yakalanan bütün JSON cevap gövdelerini döndürür."""
        payloads: list = []

        def on_response(resp):
            ct = (resp.headers or {}).get("content-type", "")
            if "application/json" not in ct:
                return
            try:
                payloads.append(resp.json())
            except Exception:  # noqa: BLE001
                pass

        page = context.new_page()
        page.on("response", on_response)
        page.goto(settings.huntr_board_url, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(3_000)
        page.close()
        return payloads

    def fetch_jobs(self) -> list[dict]:
        """Board'daki ilanları döndürür: {company,title,location,url,description} listesi."""
        if not settings.huntr_board_url:
            return []
        with sync_playwright() as pw:
            context = launch_huntr_context(pw, headless=self._headless)
            try:
                payloads = self._capture_payloads(context)
            finally:
                context.close()

        board = _find_board_payload(payloads)
        if board is None:
            logger.warning("Huntr: board payload (jobs+companies) not found in %d payloads.", len(payloads))
            return []

        # De-dupe by normalized url.
        jobs: dict[str, dict] = {}
        for job in parse_board(board):
            jobs.setdefault(job["url"].split("?", 1)[0], job)
        result = list(jobs.values())
        logger.info("Huntr: %d payloads captured, %d job(s) parsed from the board.", len(payloads), len(result))
        return result

    def dump_debug(self, out_dir: Path) -> None:
        """Alan eşlemesini kesinleştirmek için yakalanan JSON yüklerini + işlenmiş HTML'i kaydeder."""
        out_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            context = launch_huntr_context(pw, headless=self._headless)
            try:
                payloads = self._capture_payloads(context)
                page = context.new_page()
                page.goto(settings.huntr_board_url, wait_until="networkidle", timeout=60_000)
                page.wait_for_timeout(3_000)
                (out_dir / "board.html").write_text(page.content(), encoding="utf-8")
                page.close()
            finally:
                context.close()
        for i, p in enumerate(payloads):
            try:
                (out_dir / f"payload_{i:02d}.json").write_text(
                    json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:  # noqa: BLE001
                pass
        logger.info("Huntr debug dump written to %s (%d payloads).", out_dir, len(payloads))
