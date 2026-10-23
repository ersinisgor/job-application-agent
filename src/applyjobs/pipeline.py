"""CV hattının deterministik adımları: aday satır seçimi, ilan okuma, çıktı kaydetme,
Google Doc/PDF dışa aktarımı.

Burada model çağrısı YOK. CV'yi /cv-uret command'ı ile cv-writer subagent'ı üretir;
bu modüldeki fonksiyonları ise cv-tools MCP sunucusu (mcp_server.py) ve poller döngüsü
(main.py) çağırır. Değişmez kurallar (iki koşullu tetik, tekrar kontrolü, Kalkmış
işaretçisi, numaralandırma tabanı) bilerek burada, Python'da duruyor: LLM akışı yönetir
ama bu kuralları değiştiremez.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import docx_builder, drive_docs, huntr, joblookup, pdf_check
from .reporting import record_duplicate, record_failure
from .config import (
    CV_TRIGGER_BASVURU_VALUES,
    HUNTR_SEEN_FILE,
    NO_CV_MARKER,
    STATE_DIR,
    settings,
)
from .scraper import JobPage, Scraper
from .sheets import Row, SheetsClient

logger = logging.getLogger(__name__)

# Bugüne kadar verilmiş en yüksek CV numarası. Taban görevi görür: sheet'in geçici olarak
# hatalı okunması numaralandırmayı asla düşük bir değere sıfırlayıp var olan CV'lerin üzerine yazamaz.
LAST_CV_FILE = STATE_DIR / "last_cv_no"


def load_last_cv_no() -> int:
    try:
        return int(LAST_CV_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def save_last_cv_no(value: int) -> None:
    LAST_CV_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_CV_FILE.write_text(str(value), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Huntr import
# --------------------------------------------------------------------------- #

# Board'un hiç ilan döndürmediği art arda taramalar. Arka arkaya birkaç kez olursa bir kez uyarırız
# (büyük olasılıkla Huntr oturumu kapanmış), ama tek bir geçici boş okuma yok sayılır.
_huntr_empty_streak = 0


def _norm_url(url: str) -> str:
    return url.split("?", 1)[0].strip()


# Linkin içindeki LinkedIn ilan no'su, ör. .../jobs/view/4427414076/... -> 4427414076.
# M sütununun (İlan Numarası) formülüyle K'dan çıkardığı değer tam olarak budur.
_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)")


def _job_key(link: str) -> str:
    """Tekrar kontrolü için ilan başına sabit kimlik.

    LinkedIn linklerinde ilan no'sudur (M sütununun K'dan hesapladığı değer) — en güvenilir
    işaret, çünkü aynı ilanın birçok izleme URL'si olabilir. LinkedIn dışı linklerde sorgu
    kısmı atılmış URL'ye düşer. Boş link -> "".

    No'yu M sütununu doğrudan okumak yerine K'dan türetiyoruz: M bir sheet formülü, yani
    openpyxl formül metnini döndürür (ve yeni eklenmiş bir satır için Google'ın önbellekteki
    değeri eksik olabilir) — K'dan hesaplamak eşdeğer ve sağlam.
    """
    if not link:
        return ""
    m = _LINKEDIN_ID_RE.search(link)
    if m:
        return f"li:{m.group(1)}"
    return f"url:{_norm_url(link)}"


def load_huntr_seen() -> set[str] | None:
    """Board job keys already processed. None means 'first run' (no baseline yet)."""
    if not HUNTR_SEEN_FILE.exists():
        return None
    try:
        return set(json.loads(HUNTR_SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def save_huntr_seen(keys: set[str]) -> None:
    HUNTR_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    HUNTR_SEEN_FILE.write_text(json.dumps(sorted(keys)), encoding="utf-8")


def sync_huntr_to_sheet() -> int:
    """Huntr board'una yeni kaydedilen ilanları sheet'e aktarır. Eklenen satır sayısını döndürür.

    Artık varsayılan olarak KAPALI — extension panelinin "Ekle" butonu (summary_api'nin
    /add-job'u) birincil "yeni ilan -> sheet satırı" kaynağı. Bu kod, HUNTR_BOARD_URL yeniden
    ayarlanmadıkça burada etkisiz durur.

    Kimlik createdAt değil, ilan no'sudur (M sütunu / _job_key). Daha önce işlediğimiz board
    ilan anahtarlarının kalıcı bir kümesini ('seen') tutarız. Her taramada board'da yeni
    görünen bir anahtar ya:
      - içe aktarılır (henüz sheet'te değil), ya da
      - TEKRAR olarak işaretlenir (zaten sheet'te — CV üretilmez; kullanıcı record_duplicate
        ile uyarılır), sonra görüldü sayılır ki yalnızca bir kez bildirilsin.
    İlk çalışma mevcut board'u başlangıç kabul eder (hiçbir şey aktarmaz, birikmiş yığın dökülmez).
    """
    if not settings.huntr_board_url:
        return 0

    global _huntr_empty_streak
    jobs = huntr.HuntrClient(headless=True).fetch_jobs()
    if not jobs:
        _huntr_empty_streak += 1
        logger.info("Huntr: no jobs found on the board.")
        if _huntr_empty_streak == 2:  # bir kez uyar; tek bir geçici boş okumayı yok say
            record_failure(
                "huntr_board",
                error="Board okunamadı — Huntr oturumu kapanmış olabilir. "
                "Çalıştır: ./.venv/bin/python scripts/huntr_login.py",
            )
        return 0
    _huntr_empty_streak = 0

    board_keys = {_job_key(j["url"]) for j in jobs if j.get("url")}
    seen = load_huntr_seen()
    first_run = seen is None

    # Hızlı yol: board'da yeni bir şey olmayan olağan çalışma -> sheet'i okumaya gerek yok.
    if not first_run and not (board_keys - seen):
        logger.info("Huntr: no new jobs to import.")
        return 0

    sheets = SheetsClient()
    existing_by_key: dict[str, int] = {}
    for r in sheets.get_rows():
        if r.link:
            existing_by_key.setdefault(_job_key(r.link), r.number)

    if first_run:
        # İlk çalışma / geçiş: YALNIZCA sheet'te zaten takip edilen board ilanlarını başlangıç kabul et,
        # böylece birikmiş yığın için tekrar uyarısı yağmaz. Sheet'te OLMAYAN board ilanları görülmemiş
        # kalır ve aşağıda aktarılır — gerçekten bekleyen ilanlar asla yutulmaz.
        seen = board_keys & existing_by_key.keys()
        logger.info("Huntr first run: baselined %d board job(s) already in the sheet.", len(seen))

    # Info-only modunda ilan bilgisini doğrudan Huntr'dan kaydederiz (güvenilir, kaydetme anında
    # alınmış) ve N'yi işaretleriz ki CV üretilmesin — ilan sayfasını yeniden okumak yerine; o sayfa
    # çoğu zaman yanlış ya da eksik alan veren, süresi geçmiş/bayat bir LinkedIn görünümüdür.
    info_only = not settings.cv_generation

    new_keys = board_keys - seen  # henüz işlemediğimiz ilanlar
    to_import: list[dict] = []
    for j in jobs:
        key = _job_key(j["url"])
        if key not in new_keys:
            continue
        if key in existing_by_key:
            # Huntr'a yeni eklenmiş ama sheet'te zaten takip ediliyor -> uyar, aktarma.
            record_duplicate(j["url"], key, existing_by_key[key])
            continue
        entry = {"url": j["url"]}
        if info_only:
            # Yalnızca güvenilir kimlik alanlarını (şirket J, başlık L) Huntr'ın kendi kaydından doldur —
            # yeniden okuma DEĞİL. Şehir bilerek boş bırakılır: Huntr'ın coğrafi konumu çoğu zaman yanlış
            # (ör. "Krizan Bay"), bu yüzden F/H/C hatalı veri yazmak yerine kullanıcıya bırakılır.
            entry["company"] = j.get("company", "")
            entry["title"] = j.get("title", "")
        to_import.append(entry)

    # Board'da şu an olan her şeyi işlendi say ki her ilan bir kez işlensin.
    save_huntr_seen(set(seen) | board_keys)

    if not to_import:
        logger.info("Huntr: no new jobs to import (newly-seen ones were duplicates).")
        return 0

    marker = NO_CV_MARKER if info_only else None
    written = sheets.append_job_rows(to_import, cv_no_marker=marker)
    logger.info(
        "Huntr: imported %d new job(s) into rows %s%s.",
        len(written), written, " (info-only, no CV)" if info_only else "",
    )
    return len(written)


def is_candidate(row: Row) -> bool:
    """Bir satır, linki varsa, henüz CV No'su yoksa ve B "Üretilecek" diyorsa CV bekler.

    Bir değil, iki koşul. N sütunu (CV No) hâlâ "bu zaten yapıldı mı?" sorusunu cevaplar —
    dolu = yapıldı, boş = yapılacak — 'satırı sil + aynı ilanı yeniden ekle'yi çalıştıran
    budur. Ama boş bir N artık bir üretim harcamak için yeterli değil: Başvuru sütunu (B),
    kullanıcının gerçekten başvururken koyduğu bir CV_TRIGGER_BASVURU_VALUES değeri
    taşımalı. Panelden eklenen satır B boş gelir ve sadece bekler.
    """
    if not row.link:
        return False
    if row.cv_no:  # zaten bir CV numarası var
        return False
    if row.basvuru not in CV_TRIGGER_BASVURU_VALUES:
        return False
    return True


def find_candidates(rows: list[Row]) -> list[Row]:
    """Tekrar eden ilanları atılmış aday satırlar.

    Başka bir satır aynı ilanı zaten kapsıyorsa (aynı İlan Numarası / ilan no, K'dan türetilen
    M sütunu) satır atlanır (CV yok):
      - başka bir satırın o ilan için zaten bir CV No'su (N sütunu) varsa, YA DA
      - bu taramadaki daha önceki bir aday satır onu zaten sahiplendiyse.
    Böylece link iki kez eklense bile her farklı ilan tam olarak bir CV verir.
    """
    done_keys = {_job_key(r.link) for r in rows if r.cv_no and r.link}
    candidates: list[Row] = []
    seen: set[str] = set()
    for r in rows:
        if not is_candidate(r):
            continue
        key = _job_key(r.link)
        if key and (key in done_keys or key in seen):
            logger.info(
                "Row %d skipped: same job already in the sheet (job id %s).",
                r.number, key,
            )
            continue
        seen.add(key)
        candidates.append(r)
    return candidates


def save_job_description(cv_no: int, job_description: str) -> Path:
    """İlan metnini job_description_<no>.md olarak kaydeder ve yolunu döndürür.

    cv-writer subagent'ı ilanı bu dosyadan okur; /cv-yenile ve mektup da sonradan aynı
    dosyayı kullanır (ilan LinkedIn'den kalksa bile).
    """
    settings.ensure_dirs()
    jd_path = settings.job_description_dir / f"job_description_{cv_no}.md"
    jd_path.write_text(job_description, encoding="utf-8")
    return jd_path


def save_cv_markdown(cv_no: int, cv_md: str) -> Path:
    """Analiz dosyasından çıkarılan temiz CV'yi cv_<no>.md olarak kaydeder."""
    settings.ensure_dirs()
    cv_path = settings.markdown_dir / f"cv_{cv_no}.md"
    cv_path.write_text(cv_md, encoding="utf-8")
    logger.info("Saved CV -> %s", cv_path)
    return cv_path


def _export_google_doc(cv_no: int, cv_md: str) -> list[str]:
    """Şablondan .docx'i kurar, yerel DOCX klasörüne yazar, Drive'a Google Doc olarak yükler ve
    o Doc'u PDF olarak yerel PDF klasörüne geri indirir; sonra PDF'in metin katmanını denetler.

    .docx, builder'ın baytlarıdır (şablonun fontları gömülü): Workday/Taleo/iCIMS gibi portallar
    ya da Word isteyen ilanlar için. Drive'dan önce yazılır; Drive başarısız olsa da kalır.
    PDF yazılmadan önce metin katmanındaki ligatürler düzeltilir (pdf_check.fix_ligatures).

    Dönüş: kullanıcıya raporlanacak PDF uyarıları (pdf_check), boş liste = temiz. Gerçek kusurlar
    (içerik eşliği, sayfa sayısı…) failures.log'a da yazılır; ATS biçim uyarıları yalnızca loglanır,
    çünkü eski şablon (CV_TEMPLATE=cv_template_eski.docx) onları her CV'de bilerek verir.
    Best-effort: buradaki bir hata, zaten başarılı olmuş Markdown CV'yi geri almamalı. Kimlik
    bilgileri bir kez yüklensin diye tek bir Drive istemcisi yeniden kullanılır.
    """
    settings.ensure_dirs()
    pdf_path = settings.pdf_dir / f"cv_{cv_no}.pdf"
    try:
        docx_bytes = docx_builder.build_docx(cv_md)
        (settings.docx_dir / f"cv_{cv_no}.docx").write_bytes(docx_bytes)
        client = drive_docs.DriveDocsClient()
        file_id = client.upload_as_google_doc(docx_bytes, f"cv_{cv_no}")
        pdf_bytes = client.export_as_pdf(file_id)
        try:
            pdf_bytes = pdf_check.fix_ligatures(pdf_bytes)
        except Exception:  # noqa: BLE001 — Google'ın ham PDF'i yine geçerli bir CV
            logger.exception("Ligature fix failed for cv_%d; saving Google's PDF as-is.", cv_no)
        pdf_path.write_bytes(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Google Doc/PDF export failed for cv_%d (Markdown CV still saved).", cv_no)
        # Markdown CV + sheet satırı yine de başarılı olur; yani bu başka türlü sessiz kalırdı —
        # eksik bir Google Doc/PDF fark edilsin diye kaydet.
        record_failure("drive_export", cv_no=cv_no, error=repr(exc))
        return [f"Google Doc/PDF dışa aktarılamadı: {exc!r}"]

    check = pdf_check.check_cv_pdf(pdf_path, cv_md)
    if check.errors:
        record_failure("pdf_check", cv_no=cv_no, error="; ".join(check.errors))
    if check.ats:
        logger.warning("cv_%d PDF ATS warnings: %s", cv_no, "; ".join(check.ats))
    return check.messages()


def _scrape_fields(row: Row, scraper: Scraper, allow_staged: bool = False):
    """İlan sayfasını bir kez okur ve (JobPage, fields) döndürür.

    `fields`, sheet'e yazılacak yalnızca-boşsa sütun değerleridir. CV üretim yolu (cv-tools
    prepare_job) ve info-only (CV_GENERATION kapalı) yolu tarafından paylaşılır.

    allow_staged: scrape başarısız olursa ve panel bu ilanın metnini kaydettiyse
    (state/pending_jd/<job_id>.md, /add-job yazar), hatayı yaymak yerine ondan sadece
    açıklama içeren bir JobPage kurar — CV tam olarak kullanıcının panelde okuduğu metne
    dayanır. Şehir/çalışma tipi/easy-apply boş kalır, bu zararsız: _fill_page_fields boş
    değerleri atlar, böylece satır eklenirken yazılan J/L korunur.

    CV yolu dahil varsayılan olarak KAPALI. Tetik B == "Üretilecek"e taşındığından beri
    kullanıcı satırı başvuru anında işaretler; yani başarısız bir scrape büyük olasılıkla
    ilanın kalktığı anlamına gelir — ve kimsenin başvuramayacağı bir ilan için CV, ertelenmiş
    tetiğin önlemek için var olduğu israfın ta kendisidir. prepare_job (mcp_server) bunun
    yerine EXPIRED_MARKER yazar. Yine de kaydedilmiş metinden zorla üretmek için True geçir
    (run_once.py --allow-staged).
    """
    try:
        jp = scraper.fetch_job(row.link)
    except Exception as exc:  # noqa: BLE001 - RuntimeError (too short), ValueError, timeouts
        staged = (
            joblookup.load_pending_jd(joblookup.linkedin_job_id(row.link))
            if allow_staged
            else ""
        )
        if not staged:
            raise  # davranış değişmedi: satır bir sonraki taramada yeniden denenir
        logger.warning(
            "Scrape failed for row %d (%r); falling back to the %d-char description "
            "staged by the panel. City/work type stay empty.",
            row.number, exc, len(staged),
        )
        # Bildir: bu CV ilan sayfasına değil, panelin sezgisel metnine dayanıyor.
        record_failure("scrape_fallback", row=row.number, link=row.link, error=repr(exc))
        jp = JobPage(url=row.link, description=staged)
    else:
        logger.info(
            "Fetched page: %r @ %r | %s | %s (%d chars desc)",
            jp.title, jp.company, jp.city, jp.work_type, len(jp.description),
        )
    fields = {
        "C": jp.easy_apply,
        "F": jp.city,
        "H": jp.work_type,
        "L": jp.title,
        "J": jp.company,
        "J_url": jp.company_url,
    }
    return jp, fields


def _process_info_only(candidates: list[Row], sheets: SheetsClient) -> int:
    """CV üretimi KAPALI yolu: her adayın sayfasını bilgisi için okur, yalnızca-boşsa alanları
    (C/F/H/J/L) sheet'e yazar ve N'yi NO_CV_MARKER ile işaretler; satır bir kez işlenir ve ona
    asla CV atanmaz (anahtar yeniden açıldıktan sonra bile). Claude çağrısı yok, Google Doc yok,
    CV numarası harcanmaz. Yazılan satır sayısını döndürür.
    """
    count = 0
    with Scraper(headless=True) as scraper:
        for row in candidates:
            logger.info("Processing row %d (info-only, no CV) -> %s", row.number, row.link)
            try:
                # Burada bilerek allow_staged yok: bu yol SAYFANIN alanlarını istiyor ve kaydedilmiş bir
                # JobPage hiçbirini taşımaz. Ona düşmek, sıfır bilgi kazancıyla kalıcı bir NO_CV_MARKER yazardı
                # (ve böyle bir satır asla geriye dönük üretilmez). Bir sonraki taramada yeniden denemek daha iyi
                # sonuç. Pratikte panelden eklenen satırlar için zaten ulaşılmaz: CV üretimi kapalıyken /add-job
                # işaretçiyi satır eklerken yazar, yani o satırlar asla aday olmaz.
                _, fields = _scrape_fields(row, scraper)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Scrape failed for row %d; will retry next scan.", row.number
                )
                record_failure("scrape", row=row.number, link=row.link, error=repr(exc))
                continue
            try:
                sheets.write_info_only_row(row.number, fields, NO_CV_MARKER)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Sheet write failed for row %d (info-only); will retry next scan.",
                    row.number,
                )
                record_failure("sheet_write", row=row.number, link=row.link, error=repr(exc))
                continue
            count += 1
    return count


def select_candidates(
    rows: list[Row], only_row: int | None = None, limit: int | None = None
) -> list[Row]:
    """find_candidates + isteğe bağlı tek satır / adet sınırı (sheet sırasıyla)."""
    candidates = find_candidates(rows)
    if only_row is not None:
        candidates = [r for r in candidates if r.number == only_row]
        if not candidates:
            logger.warning(
                "Row %d is not a candidate (check: has link? CV No (N) empty? "
                "Başvuru (B) one of %s?).",
                only_row,
                sorted(CV_TRIGGER_BASVURU_VALUES),
            )
    if limit is not None:
        candidates = candidates[:limit]
    return candidates


def scan_candidates(
    only_row: int | None = None, limit: int | None = None
) -> tuple[SheetsClient, list[Row]]:
    """Sheet'i bir kez okuyup aday satırları döndürür. Model çağırmaz.

    Poller döngüsü bununla "iş var mı?" diye bakar; boşsa hiç agent başlatılmaz.
    """
    sheets = SheetsClient()
    # Satırı silinmiş ya da hiç üretilmemiş bekleyen ilan metinleri. Ucuz (klasörde
    # normalde 0-5 dosya olur) ve bunu yapabilecek tek uzun ömürlü süreç burası.
    joblookup.prune_pending_jd()
    rows = sheets.get_rows()
    return sheets, select_candidates(rows, only_row, limit)


def log_candidates(candidates: list[Row]) -> None:
    """Kuru çalıştırma (--dry-run) çıktısı: adayları listeler, hiçbir şey yazmaz."""
    if not candidates:
        logger.info("No candidate rows to process.")
        return
    logger.info("%d candidate row(s):", len(candidates))
    for r in candidates:
        logger.info("  [DRY] row %d | Başvuru=%r | %s", r.number, r.basvuru, r.link)
