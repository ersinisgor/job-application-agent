"""LinkedIn İlan Özeti tarayıcı eklentisinin FastAPI backend'i.

Bir iş ilanı metnini okur ve Claude ile yapılandırılmış bir özet döndürür. Alan adları
İngilizce; alan DEĞERLERİ Türkçe üretilir (bkz. summary_schema). Hızlı ve ucuz özetler
için Haiku modelini (settings.summary_model) kullanır; CV agent'larının modelinden
(settings.cv_model) bağımsızdır. Projede Anthropic API'yi doğrudan çağıran tek yer
burasıdır: özet her ilan açılışında çalıştığı için bir agent oturumuna göre çok daha
hızlı ve ucuz olmalı.

Çalıştırma:
    python scripts/run_summary_api.py
    # ya da: uvicorn src.applyjobs.summary_api:app --port 8000

Uç noktalar:
    GET  /health        -> {"status": "ok", "model": ...}
    POST /summarize     -> JobSummary
    POST /cover-letter  -> CoverLetterResponse  (panel "Mektup": gerekirse mektup agent'ı)
    POST /add-job       -> AddJobResponse       (panel "Ekle": CV için sheet'e satır ekler)

NOT: bu modül asla pipeline (ya da scraper/huntr/mcp_server) import etmemeli — onlar
Playwright'ı modül düzeyinde çeker ve bu süreç, kullanıcı LinkedIn'de elle gezinirken
çalışan süreçtir (bkz. CLAUDE.md, "Kullanıcının LinkedIn oturumunu otomatikleştirme").
Sheet/dosya erişimi temiz olan joblookup + cover_letter üzerinden yapılır.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict
from functools import lru_cache

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import cover_letter, joblookup
from .config import (
    CV_BASE_FILE,
    NO_CV_MARKER,
    PROJECTS_LIST_FILE,
    SUMMARY_CACHE_FILE,
    SUMMARY_PROMPT_FILE,
    settings,
)
from .sheets import Row, SheetLockTimeout, SheetsClient
from .summary_schema import (
    AddJobRequest,
    AddJobResponse,
    CoverLetterRequest,
    CoverLetterResponse,
    JobSummary,
    SummarizeRequest,
)

logger = logging.getLogger("applyjobs.summary")

# Adayın ana profili, bir kez yüklenir. Model her ilanın kullanıcıya ne kadar uyduğunu
# puanlayabilsin (fit_score / fit_reason) diye prompt'a eklenir. Profil = CV + geçmiş
# projelerin teknolojileri: aday CV'nin listelediğinden fazlasını biliyor (ör. bir projede
# kullanılan ama CV'de olmayan Next.js yine eşleşen beceri sayılır). İki dosya da isteğe
# bağlı; hiçbiri yüklenmezse puanlama kapanır (model fit_score = 0 yazar).
def _read_profile_file(path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("%s file %s not found.", label, path)
        return ""


_CV_TEXT = _read_profile_file(CV_BASE_FILE, "CV")
_PROJECTS_TEXT = _read_profile_file(PROJECTS_LIST_FILE, "Projects")
if not _CV_TEXT and not _PROJECTS_TEXT:
    logger.warning("No CV or projects profile loaded; fit scoring disabled.")

# Sistem prompt'u Türkçe bir dosyada (prompts/ozet_sistem.md); model alan DEĞERLERİNİ
# Türkçe yazar ki panel hızlı bir Türkçe özet gibi okunsun. Alan adları (şema) İngilizce.
SYSTEM_PROMPT = SUMMARY_PROMPT_FILE.read_text(encoding="utf-8").strip()


def _profile_block() -> str:
    """Sistem prompt'una eklenen aday profili (CV + geçmiş proje teknolojileri)."""
    parts: list[str] = []
    if _CV_TEXT:
        parts.append("CV / ÖZGEÇMİŞ:\n" + _CV_TEXT)
    if _PROJECTS_TEXT:
        parts.append(
            "Adayın yaptığı GEÇMİŞ PROJELER — burada adı geçen HER teknolojiyi, CV'de "
            "olmasa bile adayın BİLDİĞİ bir teknoloji say:\n" + _PROJECTS_TEXT
        )
    if not parts:
        return ""
    return "\n\nADAY PROFİLİ (fit_score'u buna göre puanla):\n" + "\n\n".join(parts)


# Panel puanı 70+ yeşil, 40-69 sarı, altında kırmızı boyar (extension/content.js'teki
# renderFit). Yeşil bandın dışında gerekçe YALNIZCA EKSİKLERİ saymalı ve bu yan cümle modelden
# alınmak yerine burada hesaplanır: model 'stack'i güvenilir çıkarıyor ama onu profille
# karşılaştırmakta güvenilir değil (CV ve birkaç proje PostgreSQL'i listelediği halde ona
# eksik dedi).
_FIT_GREEN_MIN = 70

_PROFILE_HAYSTACK = "\n".join(p for p in (_CV_TEXT, _PROJECTS_TEXT) if p).lower()

# Aynı teknolojinin birbirinin yerine geçen yazımları. Grubundaki HERHANGİ bir yazım profilde
# geçiyorsa zorunlu teknoloji biliniyor sayılır: ilanlar ve model ifadeyi değiştiriyor (REST API
# ve RESTful API, React ve React.js, Vector Database ve pgvector / Vector Search); yalnızca
# birebir eşleşme, adayın açıkça sahip olduğu becerileri eksik diye işaretleyip duruyordu.
# Hepsi küçük harf; girdiler sürüm/'.js' normalleştirmesinden sonra karşılaştırılır.
_SYNONYM_GROUPS: list[set[str]] = [
    {
        "rest",
        "rest api",
        "rest apis",
        "restful",
        "restful api",
        "restful apis",
        "rest endpoints",
        "restful services",
    },
    {"react", "reactjs"},
    {"node", "nodejs"},
    {"next", "nextjs"},
    {"nest", "nestjs"},
    {
        "vector database",
        "vector databases",
        "vector db",
        "vector store",
        "vector search",
        "vector retrieval",
        "pgvector",
    },
    {"sql server", "mssql", "ms sql server", "microsoft sql server"},
    # İlanlar neredeyse her zaman "GCP" yazar; profil somut servisin adını verir (Google Cloud Run).
    # Bu olmadan deployment deneyimi hiç eşleşmez.
    {"gcp", "google cloud", "google cloud platform"},
    {"postgresql", "postgres", "postgre"},
    {"mongodb", "mongo"},
    # İlanlar çoğu zaman spesifikasyon sürümünü yalın adın sonuna ekler; CV yalın biçimi yazar.
    # Sondaki rakamı topyekûn silmek 'S3', 'ES6', 'OAuth2'yi bozardı; bu yüzden bunları açıkça eşle.
    {"html", "html5"},
    {"css", "css3"},
]


def _normalize_tech(tech: str) -> str:
    """Küçük harfe çevirir, sondaki sürümü atar ('React 18' -> 'react') ve '.js' ekini siler
    ('React.js' -> 'react'); böylece yazım farkları tek bir biçimde birleşir.
    """
    t = tech.strip().lower()
    t = re.sub(r"\s+v?\d+(?:\.\d+)*$", "", t).strip()  # 'react 18', 'tailwind css v4'
    if t.endswith(".js"):
        t = t[:-3]
    return t


def _tech_variants(tech: str) -> set[str]:
    """Profilin `tech`'i bilip bilmediğine karar verirken aranacak her yazım."""
    variants = {tech.strip().lower(), _normalize_tech(tech)}
    for base in list(variants):
        for group in _SYNONYM_GROUPS:
            if base in group:
                variants |= group
    return {v for v in variants if v}


def _profile_mentions(tech: str) -> bool:
    """`tech` (ya da bilinen bir eş anlamlısı) profilin herhangi bir yerinde geçiyorsa True."""
    if not tech or not tech.strip():
        return False
    for variant in _tech_variants(tech):
        # İki taraftan sınırlı: 'Go', 'Django'yu, 'Java' da 'JavaScript'i yakalamaz; '.NET', 'Node.js'
        # ve 'C#' ise yine kendileriyle eşleşir.
        pattern = rf"(?<![a-z0-9.#+]){re.escape(variant)}(?![a-z0-9#+])"
        if re.search(pattern, _PROFILE_HAYSTACK):
            return True
    return False


def _option_known(option: str) -> bool:
    """Aday bir stack seçeneğini biliyorsa True.

    Bir seçenek bir dili framework'üyle birleştirebilir ('Java / Spring Boot'); ilan ikisini de
    istiyor, yani her parça profilde olmalı. (Alternatifler ayrı bir düzeydir: aynı stack
    grubundaki kardeş seçeneklerdir.)
    """
    parts = [part.strip() for part in option.split("/") if part.strip()]
    return bool(parts) and all(_profile_mentions(part) for part in parts)


def _stack_known(stack: list[list[str]]) -> list[list[bool]]:
    """Seçenek başına 'profilde var mı?' bayrakları — panel bunları yeşil/kırmızı boyar."""
    return [[_option_known(option) for option in group] for group in stack]


def _missing_stack(stack: list[list[str]]) -> list[str]:
    """Profilde olmayan zorunlu gruplar.

    Bir grup birbirinin yerine geçen seçenekleri listeler ('Python' ya da 'Go' ya da 'Rust');
    aday herhangi BİRİNİ bildiği anda grup karşılanmış sayılır.
    """
    missing: list[str] = []
    for group in stack:
        if group and not any(_option_known(option) for option in group):
            missing.append(" veya ".join(option.strip() for option in group))
    return missing


def _gap_only_reason(stack: list[list[str]]) -> str:
    """'Java, Spring Boot ve Kafka deneyimi yok.' — a Turkish list of gaps alone."""
    missing = _missing_stack(stack)
    if not missing:
        return ""
    listed = (
        missing[0]
        if len(missing) == 1
        else ", ".join(missing[:-1]) + " ve " + missing[-1]
    )
    return f"{listed} deneyimi yok."


def _annotate_stack(summary: JobSummary) -> None:
    """`stack_known`'u doldurur ve yeşil bandın altında `fit_reason`'u yalnızca eksiklerle yeniden yazar.

    Hiçbir şey eksik değilse (model puanı başka şekilde açıklar) ya da profil yüklenmemişse
    (fit_score zaten 0) gerekçe modele bırakılır.
    """
    if not _PROFILE_HAYSTACK:
        return
    summary.stack_known = _stack_known(summary.stack)
    if not 0 < summary.fit_score < _FIT_GREEN_MIN:
        return
    reason = _gap_only_reason(summary.stack)
    if reason:
        summary.fit_reason = reason


class MissingCredentialsError(RuntimeError):
    """Anthropic API anahtarı yapılandırılmamışsa fırlatılır."""


app = FastAPI(title="LinkedIn Job Summary", version="0.1.0")

# Extension istekleri arka plan service worker'ı üzerinden gelir (CORS olmadan çalışır), ama
# yerel geliştirme kolaylığı için CORS açık. Üretimde origin'leri kısıtla.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    """Anthropic istemcisini bir kez oluşturur (anahtar settings'ten)."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


@lru_cache(maxsize=1)
def _sheets() -> SheetsClient:
    """Sheet istemcisi, ilk kullanımda kurulur — asla import anında değil.

    SheetsClient servis hesabı anahtarını yapıcısında okur; yani onu modül düzeyinde kurmak,
    kimlik bilgilerinin olmadığı her yerde (CLAUDE.md'nin belgelediği sahte istemcili kontroller
    dahil) bu modülün import'unu başarısız yapardı.
    """
    return SheetsClient()


# Sheet satırları + ilan no indeksleri, en fazla bu sıklıkla yenilenir. Sheet'i okumak bütün
# .xlsx'i Drive'dan indirir (~1-3 sn); her panel tıklamasında tekrarlamak için fazla yavaş. Satırlar
# ve indeksler birlikte önbelleğe alınır, böylece bir ilanı çözmek en fazla BİR indirme tutar.
# _JOB_INDEX yalnızca zaten CV No'su olan satırları kapsar; _LINK_INDEX linki olan her satırı
# kapsar, /add-job'un tekrar kontrolünün ihtiyacı budur.
_SHEET_ROWS: list = []
_JOB_INDEX: dict[str, int] = {}
_LINK_INDEX: dict[str, Row] = {}
_SHEET_AT = 0.0
_SHEET_TTL = 300.0


def _sheet_snapshot(force: bool = False):
    """(rows, job_id -> cv_no, job_id -> Row); bayatsa ya da zorlanırsa yeniden indirilir."""
    global _SHEET_ROWS, _JOB_INDEX, _LINK_INDEX, _SHEET_AT
    if force or not _SHEET_ROWS or (time.monotonic() - _SHEET_AT) > _SHEET_TTL:
        _SHEET_ROWS = _sheets().get_rows()
        _JOB_INDEX = joblookup.build_job_index(_SHEET_ROWS)
        _LINK_INDEX = joblookup.build_link_index(_SHEET_ROWS)
        _SHEET_AT = time.monotonic()
        logger.info("sheet snapshot refreshed: %d rows, %d with a CV No, %d linked",
                    len(_SHEET_ROWS), len(_JOB_INDEX), len(_LINK_INDEX))
    return _SHEET_ROWS, _JOB_INDEX, _LINK_INDEX


def _resolve_job(job_id: str):
    """Bir LinkedIn ilan no'su için (cv_no, row); henüz CV No'su yoksa (None, None).

    Bir isabet bayat bir anlık görüntüden gelebilir — zararsız, çünkü CV No bir kez atanınca
    asla değişmez. Bir ISKALAMA ise 404 vermeden önce her zaman bir taze okuma tutar, çünkü CV
    agent'ı CV No'yu saniyeler önce yazmış olabilir. Iskalamalar asla önbelleğe alınmaz.
    """
    rows, index, _ = _sheet_snapshot()
    cv_no = index.get(job_id)
    if cv_no is None:
        rows, index, _ = _sheet_snapshot(force=True)
        cv_no = index.get(job_id)
    if cv_no is None:
        return None, None
    return cv_no, joblookup.find_row_for_cv_no(rows, cv_no)


def _find_job_row(job_id: str) -> Row | None:
    """Bu ilanı takip eden sheet satırı (CV No'su olsun ya da olmasın), ya da None.

    _resolve_job ile aynı biçim: bir İSABET bayat bir anlık görüntüden gelebilir (bir satır
    var olmayı bırakmaz), bir ISKALAMA ilanı yeni saymadan önce bir taze okuma tutar — CV
    agent'ı ya da elle yazılmış bir satır saniyeler önce belirmiş olabilir ve yanlış bir
    ıskalama tekrar eden bir satır ekler.
    """
    _, _, link_index = _sheet_snapshot()
    row = link_index.get(job_id)
    if row is None:
        _, _, link_index = _sheet_snapshot(force=True)
        row = link_index.get(job_id)
    return row


def _build_user_message(req: SummarizeRequest) -> str:
    parts: list[str] = []
    if req.title:
        parts.append(f"İlan başlığı: {req.title}")
    if req.company:
        parts.append(f"Şirket: {req.company}")
    if req.location:
        parts.append(f"Konum: {req.location}")
    parts.append("\nİş ilanı:\n" + req.text.strip())
    parts.append(
        "\nYukarıdaki ilanı analiz et ve istenen alanları doldur "
        "(serbest metin değerleri Türkçe)."
    )
    return "\n".join(parts)


# NOT: structured outputs (messages.parse) yerine düz JSON istemi. 14 alanlı JobSummary şeması
# özet modelinde structured outputs'un gramer derleme bütçesini aşıyor: her istek ~180 sn'lik
# derleme zaman aşımını sonuna kadar yakıp "Schema is too complex" / "Grammar compilation timed
# out" ile 400 dönüyordu. JSON istemek ve aynı Pydantic modeliyle doğrulamak cevapları saniyeler
# düzeyinde tutuyor.
_SCHEMA_JSON = json.dumps(
    JobSummary.model_json_schema(), ensure_ascii=False, separators=(",", ":")
)

_JSON_INSTRUCTION = (
    "\nYALNIZCA bu JSON şemasına uyan tek bir JSON nesnesiyle yanıt ver — markdown "
    "yok, kod bloğu yok, yorum yok:\n" + _SCHEMA_JSON
)


def _extract_json(text: str) -> str:
    """Elden geldiğince: modelin cevabından ilk {...} aralığını keser."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("Model reply contains no JSON object.")
    return text[start : end + 1]


# İlan no'suna göre anahtarlı özet önbelleği. Aynı ilan tekrar tekrar açılır — birkaç sekmede,
# hem /jobs/search-results hem /jobs/view/<id> URL'leriyle — yani (her sayfanın verdiği biraz
# farklı çıkarılmış metne göre değil) no'ya göre anahtarlamak, her ilanın tam olarak bir model
# çağrısına mal olması demektir. Uzun bir gezinti oturumu onu sınırsız büyütemesin diye sınırlı ve
# LRU ile boşaltılır; API yeniden başlasa da kalsın diye diske yansıtılır (SUMMARY_CACHE_FILE).
_SUMMARY_CACHE: "OrderedDict[str, JobSummary]" = OrderedDict()
_CACHE_MAX = 3000
# Puanlama kuralları (SYSTEM_PROMPT / prompts/ozet_sistem.md), JobSummary şeması ya da aday profili
# (profile/cv_base.md / projects.md) her değiştiğinde artır; böylece eski kurallarla dolmuş bir disk
# önbelleği eski puanları döndürmek yerine atılır.
_CACHE_VERSION = 17


def _load_cache() -> None:
    """Başlangıçta bellek içi önbelleği diskten doldurur (best-effort)."""
    try:
        raw = json.loads(SUMMARY_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return  # eksik ya da bozuk dosya: boş başla
    if not isinstance(raw, dict) or raw.get("version") != _CACHE_VERSION:
        return  # eski biçim ya da eski kurallar: bayat puanlar kalmasın diye yok say
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        return
    for job_id, data in entries.items():
        try:
            _SUMMARY_CACHE[str(job_id)] = JobSummary.model_validate(data)
        except Exception:  # noqa: BLE001 - skip entries that no longer fit the schema
            continue
    logger.info("loaded %d cached summaries from %s", len(_SUMMARY_CACHE), SUMMARY_CACHE_FILE)


def _save_cache() -> None:
    """Önbelleğin tamamını diske atomik olarak yazar (geçici dosya + replace)."""
    try:
        SUMMARY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _CACHE_VERSION,
            "entries": {k: v.model_dump(mode="json") for k, v in _SUMMARY_CACHE.items()},
        }
        tmp = SUMMARY_CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SUMMARY_CACHE_FILE)
    except OSError:
        logger.warning("could not persist summary cache to %s", SUMMARY_CACHE_FILE)


def _cache_get(job_id: str | None) -> JobSummary | None:
    if not job_id:
        return None
    summary = _SUMMARY_CACHE.get(job_id)
    if summary is not None:
        _SUMMARY_CACHE.move_to_end(job_id)  # en son kullanılan olarak işaretle
    return summary


def _cache_put(job_id: str | None, summary: JobSummary) -> None:
    if not job_id:
        return
    _SUMMARY_CACHE[job_id] = summary
    _SUMMARY_CACHE.move_to_end(job_id)
    while len(_SUMMARY_CACHE) > _CACHE_MAX:
        _SUMMARY_CACHE.popitem(last=False)  # evict least-recently used
    _save_cache()


_load_cache()


def _summary_is_blank(summary: JobSummary) -> bool:
    """Model kullanılabilir hiçbir şey döndürmediyse True — her alan boş, stack yok, uyum yok.
    Bu, modele verilen metnin aslında bir ilan olmadığı anlamına gelir (extension bazen yanlış
    kapsayıcıyı okuyor); böyle bir sonuç önbelleğe alınmamalı, yoksa ilan sonraki her açılışta
    boş özeti döndürmeye devam ederdi.
    """
    return not (
        summary.job_title.strip()
        or summary.company.strip()
        or summary.role_summary.strip()
        or summary.work_type_note.strip()
        or summary.min_experience.strip()
        or summary.fit_score
        or any(any(opt.strip() for opt in group) for group in summary.stack)
    )


def summarize(req: SummarizeRequest) -> JobSummary:
    """Bir iş ilanı metnini yapılandırılmış (değerleri Türkçe) bir özete çevirir."""
    if not settings.anthropic_api_key:
        raise MissingCredentialsError(
            "ANTHROPIC_API_KEY is not set. Add it to the project .env file."
        )

    # Bir yenileme (panelin "Yenile" butonu) önbellekten OKUMAYI atlar ama aşağıda saklanan girdinin
    # yine üzerine yazar — sayfanın o an verdiği metinden yeniden hesaplar.
    if not req.refresh:
        cached = _cache_get(req.job_id)
        if cached is not None:
            logger.info("summary cache hit for job %s", req.job_id)
            return cached

    # CV + prompt + şema öneki kullanıcının baktığı her ilan için aynı; bu yüzden önbelleğe al —
    # sadece ilana özel kullanıcı mesajı değişir. (Haiku'nun 4096 token'lık önbelleklenebilir
    # asgarisinin altında sessizce etkisiz kalır; zararsız.)
    system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT + _profile_block() + _JSON_INSTRUCTION,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    last_error: Exception | None = None
    for _ in range(2):  # bozuk JSON'da bir kez yeniden dene
        response = _client().messages.create(
            model=settings.summary_model,
            max_tokens=600,  # özet bilerek kısa; gecikmeyi de sınırla
            temperature=0,  # deterministik: aynı ilan her seferinde aynı puanı alır
            system=system,
            messages=[{"role": "user", "content": _build_user_message(req)}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            summary = JobSummary.model_validate_json(_extract_json(text))
            _annotate_stack(summary)
            # Boş bir sonucu saklama: okunan metin bir ilan değildi; sonraki bir açılış (gerçek açıklama
            # yüklenince) yeniden hesaplasın.
            if _summary_is_blank(summary):
                logger.info("blank summary for job %s; not caching", req.job_id)
            else:
                _cache_put(req.job_id, summary)
            return summary
        except Exception as exc:  # noqa: BLE001 - malformed JSON: retry once
            last_error = exc
    raise ValueError(f"Model did not return valid JSON: {last_error}")


def _http_from(exc: Exception, what: str) -> HTTPException:
    """Bir model/kimlik bilgisi hatasını panelin beklediği HTTP durumuna eşler.

    İki uç nokta paylaşır ki hata işleme birbirinden kopmasın. `what`, genel mesaj için
    işlemin adını verir.
    """
    if isinstance(exc, SheetLockTimeout):
        return HTTPException(
            status_code=503,
            detail="Tablo şu anda güncelleniyor; birkaç saniye sonra tekrar dene.",
        )
    if isinstance(exc, MissingCredentialsError):
        return HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        return HTTPException(
            status_code=429,
            detail="Claude API rate limit hit. Please try again shortly.",
        )
    if isinstance(exc, anthropic.AuthenticationError):
        return HTTPException(
            status_code=500,
            detail="Claude API authentication failed (check ANTHROPIC_API_KEY).",
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return HTTPException(
            status_code=502,
            detail="Could not reach the Claude API. Check your internet connection.",
        )
    if isinstance(exc, anthropic.APIStatusError):
        logger.exception("Claude API error")
        return HTTPException(status_code=502, detail=f"Claude API error ({exc.status_code}).")
    logger.exception("Unexpected error during %s", what)
    return HTTPException(status_code=500, detail=f"Unexpected error during {what}.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.summary_model}


@app.post("/summarize", response_model=JobSummary)
def summarize_endpoint(req: SummarizeRequest) -> JobSummary:
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="Job text ('text') must not be empty.")

    try:
        return summarize(req)
    except Exception as exc:  # noqa: BLE001 - mapped to a status by _http_from
        raise _http_from(exc, "summarization")


_COVER_LOCK = threading.Lock()


@app.post("/cover-letter", response_model=CoverLetterResponse)
def cover_letter_endpoint(req: CoverLetterRequest) -> CoverLetterResponse:
    """Bu ilanın mektubunu döndürür; yalnızca henüz yoksa (mektup agent'ıyla) üretir."""
    if not req.job_id or not req.job_id.strip():
        raise HTTPException(status_code=422, detail="'job_id' must not be empty.")
    if req.lang not in cover_letter.LANGS:
        raise HTTPException(
            status_code=422,
            detail=f"Bilinmeyen dil: {req.lang!r} (geçerli: {', '.join(cover_letter.LANGS)})",
        )

    try:
        cv_no, row = _resolve_job(req.job_id.strip())
    except FileNotFoundError as exc:  # service account missing
        logger.exception("Sheet unavailable")
        raise HTTPException(status_code=500, detail=f"Sheet okunamadı: {exc}")

    if cv_no is None:
        # Çok farklı iki durum eskiden tek bir mesajı paylaşıyordu ve "önce CV üretilmeli", ilan hiç
        # eklenmemiş olsa bile "sırada" gibi okunuyordu. No'yu yazmak, panelin ekrandakinden FARKLI bir
        # ilanı çözdüğü durumu da görünür kılar — yoksa panelden görünmezdi.
        job_id = req.job_id.strip()
        row = _find_job_row(job_id)
        if row is None:
            logger.info("cover-letter: job %s is not in the sheet at all", job_id)
            detail = f"Bu ilan ({job_id}) tabloda yok — önce \"Ekle\" ile ekle."
        else:
            logger.info("cover-letter: job %s is at row %d but has no CV No yet",
                        job_id, row.number)
            detail = f"Bu ilan tabloda (satır {row.number}) ama CV'si henüz üretilmedi."
        raise HTTPException(status_code=404, detail=detail)

    try:
        # Mektup bir claude -p agent çalışması (~30-60 sn). Çift tıklama aynı mektubu iki
        # kez ürettirmesin diye üretimler sıraya alınır; önbellekten okuma da kilidin
        # içinde, çünkü ikinci tıklama birincinin yazdığı dosyayı görmeli.
        with _COVER_LOCK:
            text, created = cover_letter.get_or_create(
                cv_no, lang=req.lang, force=req.force, row=row
            )
    except (FileNotFoundError, ValueError) as exc:
        # Eksik CV / eksik kayıtlı ilan metni / boş şirket: hepsi "üretilemez", hata değil.
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        # Agent çalıştı ama dosya üretmedi: mesaj kullanıcıya olduğu gibi gösterilir.
        logger.warning("cover-letter agent failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _http_from(exc, "cover letter generation")

    return CoverLetterResponse(text=text, cv_no=cv_no, lang=req.lang, created=created)


# --- /add-job: panelin "Ekle" butonu ----------------------------------------
# "Yeni ilan -> sheet satırı" kaynağı olarak Huntr aktarımının yerini aldı. Yalnızca link (K),
# başlık (L) ve şirket (J) yazar, CV No'yu (N) boş bırakır; bu pipeline.is_candidate'in aradığı
# biçimin tam olarak kendisi — kullanıcı B'yi "Üretilecek" yapınca CV agent'ı satırı alır.

_JOB_VIEW_URL = "https://www.linkedin.com/jobs/view/{}/"

# FastAPI senkron uç noktaları bir thread havuzunda çalıştırır; bu yüzden bir çift tıklama iki
# isteği aynı anda _find_job_row'a sokabilir: ikisi de ıskalar, ikisi de ekler, bir ilan için iki
# satır. Bu yüzden kontrol-sonra-ekle bütünü süreç içinde sıraya konur. (sheets.sheet_lock yalnızca
# yüklemenin kendisini ve yalnızca SÜREÇLER ARASINDA korur.)
_ADD_LOCK = threading.Lock()


def _canonical_link(job_id: str, url: str) -> str:
    """Panel ne gönderirse göndersin bir /jobs/view/<id>/ linki.

    /jobs/search-results'ta sayfa URL'si "?currentJobId=<id>" biçimindedir ve "/jobs/view/"
    içermez. Bunu K'ya yazmak M sütununun formülünü, pipeline._job_key'i ve sonraki her tekrar
    kontrolünü bozardı — sessizce. Bu yüzden verilen URL aynı no'yu zaten taşımıyorsa link
    no'dan yeniden kurulur.
    """
    url = (url or "").strip()
    if url and joblookup.linkedin_job_id(url) == job_id:
        return url.split("?", 1)[0]
    return _JOB_VIEW_URL.format(job_id)


def _remember_appended_row(job_id: str, row_number: int, link: str, job: dict,
                           marker: str | None) -> None:
    """Az önce eklenen satırı önbellekteki anlık görüntüye ekler.

    İkinci bir tıklama 5 dakikalık TTL'i beklemeden ve bir kez daha bütün .xlsx'i indirmeden
    "exists" görmeli. Yapay satır sayısal bir N taşımaz; yani _JOB_INDEX ve find_row_for_cv_no
    etkilenmez.
    """
    row = Row(
        number=row_number,
        cells={
            "J": job.get("company", ""),
            "K": link,
            "L": job.get("title", ""),
            "N": marker or "",
        },
    )
    _SHEET_ROWS.append(row)
    _LINK_INDEX[job_id] = row


@app.post("/add-job", response_model=AddJobResponse)
def add_job_endpoint(req: AddJobRequest) -> AddJobResponse:
    """Bu ilanı sheet'e ekler; kullanıcı B'yi "Üretilecek" yapınca CV agent'ı alır."""
    job_id = (req.job_id or "").strip()
    if not job_id:
        raise HTTPException(status_code=422, detail="'job_id' must not be empty.")
    if not job_id.isdigit():
        raise HTTPException(status_code=422, detail=f"Geçersiz ilan no: {job_id!r}")

    link = _canonical_link(job_id, req.url)

    with _ADD_LOCK:
        try:
            row = _find_job_row(job_id)
        except FileNotFoundError as exc:  # service account missing
            logger.exception("Sheet unavailable")
            raise HTTPException(status_code=500, detail=f"Sheet okunamadı: {exc}")
        except Exception as exc:  # noqa: BLE001
            raise _http_from(exc, "sheet read")

        if row is not None:
            # Zaten takip ediliyor — asla ikinci bir satır ekleme (find_candidates zaten atlardı). Satır
            # hâlâ CV'sizken metni yeniden kaydet: kullanıcı tam da ilk scrape başarısız olduğu için yeniden
            # tıklıyor olabilir.
            staged = (
                joblookup.save_pending_jd(job_id, req.description)
                if not row.cv_no
                else False
            )
            logger.info("add-job: %s already at row %d (N=%r)", job_id, row.number, row.cv_no)
            return AddJobResponse(
                status="exists", row=row.number, cv_no=row.cv_no, staged=staged
            )

        # Eklemeden ÖNCE kaydet: yedeği olmayan eklenmiş bir satır sessizce eski davranışa düşer;
        # sahipsiz kaydedilmiş bir dosya ise zararsızdır (eşleşen satır olmadan asla okunmaz ve
        # temizlenir).
        try:
            staged = joblookup.save_pending_jd(job_id, req.description)
        except OSError:
            logger.warning("Could not stage the description for job %s", job_id)
            staged = False

        marker = None if settings.cv_generation else NO_CV_MARKER
        job = {
            "url": link,
            "title": (req.title or "").strip(),
            "company": (req.company or "").strip(),
        }
        try:
            written = _sheets().append_job_rows([job], cv_no_marker=marker)
        except Exception as exc:  # noqa: BLE001
            if staged:
                joblookup.clear_pending_jd(job_id)  # satırı olmayan bir dosya bırakma
            raise _http_from(exc, "sheet append")

        row_number = written[0]
        _remember_appended_row(job_id, row_number, link, job, marker)

    logger.info("add-job: appended row %d for job %s (staged=%s, marker=%r)",
                row_number, job_id, staged, marker)
    return AddJobResponse(
        status="added", row=row_number, cv_no=marker or "", staged=staged
    )
