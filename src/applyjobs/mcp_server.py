"""cv-tools: agent'ların dış dünyaya dokunduğu tek kapı (MCP sunucusu, stdio).

Claude Code bu sunucuyu .mcp.json üzerinden başlatır. Agent'lar (orkestratör command'lar
ve subagent'lar) sheet'e, LinkedIn'e (misafir görünümü), Google Drive'a hiçbir zaman
doğrudan erişmez; her şey buradaki araçlardan geçer.

Tasarım ilkesi: değişmezler araçlarda, muhakeme agent'larda. CV numarası ayırma,
"Kalkmış" işaretleme, tekrar kontrolü, sheet kilidi ve çıktı ayrıştırma mevcut Python
kodunda kalır (pipeline, sheets, cv_output, cover_letter). Agent yanlış bir numara yazsa
ya da bir adımı atlasa bile sheet bozulmaz: numara ve satır alanları sunucunun belleğinde
tutulur, agent'tan geri okunmaz.

Önemli: stdout MCP protokolüne ayrılmıştır. Loglar stderr'e ve state/mcp.log'a gider.
Playwright (scraper) sadece prepare_job içinde, ihtiyaç anında import edilir; mektup
oturumunda hiç yüklenmez.
"""
from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import cover_letter, cv_output, docx_builder, joblookup
from .config import EXPIRED_MARKER, STATE_DIR, settings
from .reporting import LOG_DATEFMT, LOG_FORMAT, record_failure
from .sheets import SheetsClient

logger = logging.getLogger("applyjobs.mcp")

server = MCPServer(
    name="cv-tools",
    instructions=(
        "Job Application Agent'ın deterministik araçları: aday satırlar, ilan okuma, CV'yi "
        "sonlandırma (docx → Google Doc → PDF + sheet), yeniden üretim ve mektup."
    ),
)

# prepare_job ile ayrılan ama henüz finalize_cv ile kesinleşmeyen satırlar:
# satır no → {"cv_no", "fields", "link", "started"}. Numara sadece sheet yazımı başarılı
# olunca harcanır (eski run_scan davranışı); oturum biterse ayrılan numara kaybolmaz.
_RESERVED: dict[int, dict] = {}

# regen_targets ile başlayan yeniden üretimler: CV no → {"row", "started"}.
_REGEN: dict[int, dict] = {}


def _setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(LOG_FORMAT, LOG_DATEFMT)
    err = logging.StreamHandler(sys.stderr)
    err.setFormatter(fmt)
    root.addHandler(err)
    # Ayrı dosya: state/agent.log'u poller süreci döndürüyor; iki süreç aynı dosyayı
    # döndürürse birbirinin çıktısını keser (bkz. reporting.setup_console_logging).
    fh = RotatingFileHandler(
        STATE_DIR / "mcp.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _analysis_path(cv_no: int) -> Path:
    return settings.analysis_dir / f"cv_{cv_no}_analysis.md"


def _review_path(cv_no: int) -> Path:
    return settings.analysis_dir / f"cv_{cv_no}_review.md"


def _read_agent_output(cv_no: int, started: float) -> tuple[str, float | None, str]:
    """Agent'ın bu çalışmada yazdığı analiz (ve varsa review) dosyasını ayrıştırır.

    Eski generate+review mantığının aynısı: CV ve eşleşme oranı review'dan (varsa),
    öncelikli diller ilk üretimden gelir. Dosya bu çalışma başladıktan SONRA yazılmamışsa
    hata verir; yoksa önceki bir denemenin bayat dosyası sessizce kullanılırdı.
    """
    analysis = _analysis_path(cv_no)
    if not analysis.exists() or analysis.stat().st_mtime < started:
        raise FileNotFoundError(
            f"cv-writer bu çalışmada analiz dosyasını yazmadı: {analysis}"
        )
    full = analysis.read_text(encoding="utf-8")
    cv_md, match_rate, languages = cv_output.parse_agent_output(full)

    review = _review_path(cv_no)
    if settings.cv_review and review.exists() and review.stat().st_mtime >= started:
        review_full = review.read_text(encoding="utf-8")
        cv_md = cv_output.extract_cv(review_full)
        reviewed_rate = cv_output.extract_match_rate(review_full)
        if reviewed_rate is not None:
            match_rate = reviewed_rate

    parsed = docx_builder.parse_markdown_cv(cv_md)
    if not parsed.get("experience") or not parsed.get("projects"):
        raise ValueError(
            "CV ayrıştırılamadı (deneyim ya da proje bölümü boş) — .docx şablonun "
            "donmuş metniyle çıkardı. Analiz dosyasındaki CV biçimini düzeltin."
        )
    return cv_md, match_rate, languages


def _sheet_rows():
    sheets = SheetsClient()
    return sheets, sheets.get_rows()


@server.tool()
def cv_candidates(only_row: int | None = None, limit: int | None = None) -> dict:
    """CV bekleyen satırları listeler (link var, N boş, B == "Üretilecek", tekrar değil).

    Hiçbir şey yazmaz. cv_generation=false ise CV üretilmemeli (info-only modu poller'da).
    """
    from . import pipeline  # Playwright zinciri; sadece CV araçlarında yüklenir

    sheets, rows = _sheet_rows()
    joblookup.prune_pending_jd()
    candidates = pipeline.select_candidates(rows, only_row, limit)
    return {
        "cv_generation": settings.cv_generation,
        "cv_review": settings.cv_review,
        "candidates": [
            {
                "row": r.number,
                "link": r.link,
                "company": r.get("J"),
                "title": r.get("L"),
                "basvuru": r.basvuru,
            }
            for r in candidates
        ],
    }


@server.tool()
def prepare_job(row: int, allow_staged: bool = False) -> dict:
    """Bir aday satırın ilanını okur ve CV için hazırlar.

    - İlan okunamazsa (büyük olasılıkla kalkmış): N = "Kalkmış" yazılır, CV numarası
      harcanmaz, status="expired" döner. Bu satır için CV ÜRETME.
    - Okunursa: CV numarası ayrılır, ilan metni job_description_<no>.md'ye yazılır ve
      cv-writer'a verilecek yollar + relocation kuralı döner (status="ready").
    allow_staged=True: ilan okunamazsa panelin kaydettiği metinle devam et (bilinçli istisna).
    """
    from . import pipeline
    from .scraper import Scraper

    sheets, rows = _sheet_rows()
    target = next((r for r in pipeline.find_candidates(rows) if r.number == row), None)
    if target is None:
        return {"status": "not_candidate", "row": row,
                "message": "Satır aday değil (link, boş N ve B='Üretilecek' gerekli)."}

    with Scraper(headless=True) as scraper:
        try:
            jp, fields = pipeline._scrape_fields(target, scraper, allow_staged=allow_staged)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Posting unavailable for row %d (%r); marking N=%r.",
                           row, exc, EXPIRED_MARKER)
            record_failure("expired", row=row, link=target.link, error=repr(exc))
            try:
                sheets.write_info_only_row(row, {}, EXPIRED_MARKER)
            except Exception as write_exc:  # noqa: BLE001
                record_failure("sheet_write", row=row, link=target.link, error=repr(write_exc))
                return {"status": "error", "row": row,
                        "message": f"İlan okunamadı ve 'Kalkmış' yazılamadı: {write_exc!r}"}
            return {"status": "expired", "row": row,
                    "message": "İlan artık okunamıyor; N='Kalkmış' yazıldı, CV üretilmeyecek."}

    # Asla bugüne kadar verilmiş en yüksek numaranın altına inme (taban koruması) ve bu
    # oturumda başka satıra ayrılmış numarayı tekrar verme.
    reserved = [v["cv_no"] for v in _RESERVED.values()]
    cv_no = max(
        sheets.next_cv_number(rows),
        pipeline.load_last_cv_no() + 1,
        max(reserved, default=0) + 1,
    )
    jd_path = pipeline.save_job_description(cv_no, jp.description)
    # Bu numara hiçbir sheet satırına ait değil, yani eski bir denemenin dosyaları bayattır.
    for stale in (_analysis_path(cv_no), _review_path(cv_no)):
        stale.unlink(missing_ok=True)

    _RESERVED[row] = {"cv_no": cv_no, "fields": fields, "link": target.link,
                      "started": time.time()}
    city = target.city or jp.city
    logger.info("Row %d prepared as CV No %d (%d chars).", row, cv_no, len(jp.description))
    return {
        "status": "ready",
        "row": row,
        "cv_no": cv_no,
        "company": jp.company or target.get("J"),
        "title": jp.title or target.get("L"),
        "job_description_path": str(jd_path),
        "analysis_path": str(_analysis_path(cv_no)),
        "review_path": str(_review_path(cv_no)),
        "relocation_rule": cv_output.relocation_instruction(target.work_mode, city),
        "cv_review": settings.cv_review,
    }


@server.tool()
def finalize_cv(row: int) -> dict:
    """cv-writer (ve açıksa cv-reviewer) bittikten sonra CV'yi kesinleştirir.

    Analiz dosyasından temiz CV'yi çıkarır → cv_<no>.md, .docx → Google Doc → PDF
    (best-effort), sheet'e N/P/Q + okunan alanları tek seferde yazar, numarayı harcar.
    """
    from . import pipeline

    res = _RESERVED.get(row)
    if res is None:
        return {"status": "error", "row": row,
                "message": "Bu satır için prepare_job çağrılmamış."}
    cv_no = res["cv_no"]
    try:
        cv_md, match_rate, languages = _read_agent_output(cv_no, res["started"])
    except (FileNotFoundError, ValueError) as exc:
        record_failure("generate", row=row, cv_no=cv_no, link=res["link"], error=repr(exc))
        return {"status": "error", "row": row, "cv_no": cv_no, "message": str(exc)}

    pipeline.save_cv_markdown(cv_no, cv_md)
    # Hata olursa kendisi kaydeder, CV kalır. Uyarılar orkestratörün raporuna gider.
    pdf_warnings = pipeline._export_google_doc(cv_no, cv_md)

    try:
        SheetsClient().write_processed_row(row, res["fields"], cv_no, match_rate, languages)
    except Exception as exc:  # noqa: BLE001
        record_failure("sheet_write", row=row, cv_no=cv_no, link=res["link"], error=repr(exc))
        return {"status": "error", "row": row, "cv_no": cv_no,
                "message": f"CV dosyaları kaydedildi ama sheet yazılamadı: {exc!r}"}

    pipeline.save_last_cv_no(cv_no)
    # İlan metni artık job_description_<no>.md'de; panelin geçici kopyası silinir. Sheet
    # yazımından SONRA, bilerek: yazım başarısız olursa yedek bir sonraki deneme için kalır.
    joblookup.clear_pending_jd(joblookup.linkedin_job_id(res["link"]))
    _RESERVED.pop(row, None)
    pdf = settings.pdf_dir / f"cv_{cv_no}.pdf"
    docx = settings.docx_dir / f"cv_{cv_no}.docx"
    logger.info("CV %d done for row %d (match rate %s).", cv_no, row, match_rate)
    return {
        "status": "done",
        "row": row,
        "cv_no": cv_no,
        "match_rate": match_rate,
        "languages": languages,
        "cv_path": str(settings.markdown_dir / f"cv_{cv_no}.md"),
        "pdf_path": str(pdf) if pdf.exists() else None,
        "docx_path": str(docx) if docx.exists() else None,
        "pdf_warnings": pdf_warnings,
    }


@server.tool()
def regen_targets(start: int, end: int, instruction: str = "") -> dict:
    """CV No'su [start, end] aralığındaki CV'leri yeniden üretim için hazırlar.

    Kaydedilmiş ilan metni kullanılır (yeniden okuma yok). instruction verilirse
    cv-writer'a AYNEN iletilecek talimat bloğu da döner (dürüstlük sözleşmesi geçerli).
    """
    _, rows = _sheet_rows()
    targets = joblookup.targets_in_range(rows, start, end)
    started = time.time()
    items = []
    for cv_no, r in targets:
        jd_path = settings.job_description_dir / f"job_description_{cv_no}.md"
        try:
            joblookup.load_saved_jd(cv_no)
        except (FileNotFoundError, ValueError) as exc:
            items.append({"cv_no": cv_no, "row": r.number, "status": "missing_jd",
                          "message": str(exc)})
            continue
        _REGEN[cv_no] = {"row": r.number, "started": started}
        items.append({
            "cv_no": cv_no,
            "row": r.number,
            "status": "ready",
            "job_description_path": str(jd_path),
            "analysis_path": str(_analysis_path(cv_no)),
            "review_path": str(_review_path(cv_no)),
            "relocation_rule": cv_output.relocation_instruction(r.work_mode, r.city),
        })
    return {
        "cv_review": settings.cv_review,
        "instruction_block": cv_output.extra_instruction_block(instruction),
        "targets": items,
    }


@server.tool()
def finalize_regen(cv_no: int) -> dict:
    """Yeniden üretilen CV'yi kesinleştirir: cv_<no>.md, aynı adlı Google Doc + PDF,
    Match Rate (P). Diğer sheet sütunlarına dokunulmaz."""
    from . import pipeline

    info = _REGEN.get(cv_no)
    if info is None:
        return {"status": "error", "cv_no": cv_no,
                "message": "Bu CV için regen_targets çağrılmamış."}
    try:
        cv_md, match_rate, _ = _read_agent_output(cv_no, info["started"])
    except (FileNotFoundError, ValueError) as exc:
        record_failure("regenerate", row=info["row"], cv_no=cv_no, error=repr(exc))
        return {"status": "error", "cv_no": cv_no, "message": str(exc)}

    pipeline.save_cv_markdown(cv_no, cv_md)
    pdf_warnings = pipeline._export_google_doc(cv_no, cv_md)
    if match_rate is not None:
        try:
            SheetsClient().write_match_rate(info["row"], match_rate)
        except Exception:  # noqa: BLE001
            logger.exception("Match-rate write failed for CV %d (files were saved).", cv_no)
    _REGEN.pop(cv_no, None)
    docx = settings.docx_dir / f"cv_{cv_no}.docx"
    return {"status": "done", "cv_no": cv_no, "match_rate": match_rate,
            "docx_path": str(docx) if docx.exists() else None,
            "pdf_warnings": pdf_warnings}


@server.tool()
def cover_letter_context(cv_no: int, lang: str = "en", force: bool = False) -> dict:
    """Mektup için girdileri verir. Mektup zaten varsa (ve force yoksa) metnini döndürür:
    dosyanın kendisi önbellektir, yeniden üretme."""
    path = cover_letter.cover_letter_path(cv_no, lang)
    if not force and path.exists():
        return {"status": "exists", "text": cover_letter._read_letter(path)}
    try:
        inputs = cover_letter.letter_inputs(cv_no, lang)
    except (FileNotFoundError, ValueError) as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "ready", **inputs}


@server.tool()
def save_cover_letter(cv_no: int, lang: str, letter: str) -> dict:
    """cover-letter-writer'ın yazdığı mektubu kaydeder. İmza bloğu birebir değilse
    hata döner; mektubu düzeltip tekrar çağır."""
    try:
        path = cover_letter.save_letter(cv_no, lang, letter)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "saved", "path": str(path)}


def main() -> None:
    _setup_logging()
    server.run("stdio")


if __name__ == "__main__":
    main()
