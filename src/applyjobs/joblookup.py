"""Bir ilanın sheet satırını bulur ve ilan metnini CV No'ya ya da ilan no'suna göre okur/kaydeder.

CV agent'larının MCP sunucusu (mcp_server), mektup özelliği (cover_letter, summary_api) ve
panelin "Ekle" butonu (summary_api -> /add-job) tarafından paylaşılır.

ÖNEMLİ: bu modül asla pipeline/scraper/huntr import etmemeli. Onlar Playwright'ı modül
düzeyinde çeker ve summary_api bunu import eder — API süreci LinkedIn'e dokunamaz kalmalı
(bkz. CLAUDE.md, "Kullanıcının LinkedIn oturumunu otomatikleştirme"). Buraya yalnızca
config + sheets ait.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from .config import (
    PENDING_JD_DIR,
    PENDING_JD_MAX_AGE_DAYS,
    PENDING_JD_MIN_CHARS,
    settings,
)
from .sheets import Row, SheetsClient

logger = logging.getLogger("applyjobs.joblookup")

# Bir linkin içindeki LinkedIn ilan no'su, ör. .../jobs/view/4427414076/... -> 4427414076.
# pipeline._job_key'in regex'ini import etmek yerine bilerek kopyalar: o fonksiyon poller'ın
# tekrar kontrolü için önekli bir "li:<id>" anahtarı döndürür ve Playwright import zincirinin
# arkasında yaşar. DESENİ pipeline.py İLE SENKRON TUT.
_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)")


def linkedin_job_id(link: str) -> str:
    """Bir sheet linkinden yalın LinkedIn ilan no'su, ör. "4427414076". LinkedIn değilse "".

    Yalın ("li:" öneki yok), böylece extension'ın getCurrentJobId()'sinin gönderdiğiyle
    API sınırında hiçbir çeviri olmadan eşleşir.
    """
    if not link:
        return ""
    m = _LINKEDIN_ID_RE.search(link)
    return m.group(1) if m else ""


def find_row_for_cv_no(rows: list[Row], cv_no: int) -> Row | None:
    """CV No'su (N sütunu) tam olarak cv_no olan satır. Yoksa None."""
    for r in rows:
        if SheetsClient._as_int(r.cv_no) == cv_no:
            return r
    return None


def targets_in_range(rows: list[Row], start: int, end: int) -> list[tuple[int, Row]]:
    """Sayısal CV No'su [start, end] aralığında olan (cv_no, row) çiftleri, cv_no'ya göre sıralı."""
    targets = [
        (n, r)
        for r in rows
        if (n := SheetsClient._as_int(r.cv_no)) is not None and start <= n <= end
    ]
    targets.sort(key=lambda t: t[0])
    return targets


def build_job_index(rows: list[Row]) -> dict[str, int]:
    """Yalın LinkedIn ilan no'su -> CV No; linki ve sayısal N'si olan her satır için."""
    index: dict[str, int] = {}
    for r in rows:
        job_id = linkedin_job_id(r.link)
        n = SheetsClient._as_int(r.cv_no)
        if job_id and n is not None:
            index[job_id] = n
    return index


def build_link_index(rows: list[Row]) -> dict[str, Row]:
    """Yalın LinkedIn ilan no'su -> o linki taşıyan İLK satır, CV No'su olsun ya da olmasın.

    build_job_index() yalnızca zaten sayısal N'si olan satırları görür; bu yüzden "bu ilan
    zaten sheet'te mi, hâlâ CV'sini mi bekliyor?" sorusunu cevaplayamaz — /add-job'un
    ihtiyaç duyduğu tekrar kontrolü tam olarak budur. sync_huntr_to_sheet gibi ilk satır kazanır.
    """
    index: dict[str, Row] = {}
    for r in rows:
        job_id = linkedin_job_id(r.link)
        if job_id:
            index.setdefault(job_id, r)
    return index


def load_saved_jd(cv_no: int) -> str:
    """CV ilk üretildiğinde kaydedilen ilan metni, kırpılmış.

    Yeniden üretimi ve istendiğinde üretilen mektupları süresi geçmiş/kaldırılmış LinkedIn
    ilanlarına karşı sağlam yapan, bunun yeniden kullanılmasıdır.
    """
    jd_path = settings.job_description_dir / f"job_description_{cv_no}.md"
    if not jd_path.exists():
        raise FileNotFoundError(f"Saved job description not found: {jd_path}")
    job_description = jd_path.read_text(encoding="utf-8").strip()
    if not job_description:
        raise ValueError(f"Saved job description is empty: {jd_path}")
    return job_description


# --- Panelin "Ekle" butonunun kaydettiği ilan metinleri ----------------------------
# Panel ilanı özetlemek için zaten okuyor; bu yüzden /add-job o metni yeni satırın yanına
# kaydeder. Misafir görünümlü scrape BİRİNCİL kaynak olarak kalır; kaydedilen kopya yalnızca o
# scrape başarısız olursa (ve --allow-staged istenirse) okunur, CV oluşunca da silinir (o andan
# sonra yeniden üretimin/mektubun kullandığı kayıt job_description_<no>.md'dir).


def pending_jd_path(job_id: str) -> Path:
    """Yalın bir LinkedIn ilan no'su için state/pending_jd/<job_id>.md.

    Sayısal olmayan her şeyi reddeder: job_id extension'dan HTTP üzerinden gelir; yani bu bir
    akıl sağlığı kontrolü olduğu kadar yol geçişi (path traversal) korumasıdır da.
    """
    if not job_id or not job_id.isdigit():
        raise ValueError(f"Not a LinkedIn job id: {job_id!r}")
    return PENDING_JD_DIR / f"{job_id}.md"


def save_pending_jd(job_id: str, text: str) -> bool:
    """Panelin ilan metnini kaydeder. Çok kısaysa False (ve hiçbir şey yazılmaz).

    Atomik (tmp + replace), böylece okuyan taraf asla yarım yazılmış bir dosya görmez.
    """
    text = (text or "").strip()
    if len(text) < PENDING_JD_MIN_CHARS:
        return False
    path = pending_jd_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


def load_pending_jd(job_id: str) -> str:
    """Kaydedilen metin; yoksa/çok kısaysa/okunamıyorsa "".

    Asla hata fırlatmaz: bu bir yedek yol, bir scrape hatasını başka bir hataya
    dönüştürmemeli.
    """
    try:
        text = pending_jd_path(job_id).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""
    return text if len(text) >= PENDING_JD_MIN_CHARS else ""


def clear_pending_jd(job_id: str) -> None:
    """CV'si yazılınca kaydedilen metni siler."""
    try:
        pending_jd_path(job_id).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def prune_pending_jd(max_age_days: int = PENDING_JD_MAX_AGE_DAYS) -> int:
    """Delete staged files older than max_age_days; return how many were removed."""
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        entries = list(PENDING_JD_DIR.glob("*.md"))
    except OSError:
        return 0
    for path in entries:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("Pruned %d stale staged job description(s).", removed)
    return removed
