"""Playwright ile iş ilanı okuyucu (scraper).

Sheet'in "İlan Linki" (K) sütunundaki URL'ye gider — şirket kariyer siteleri ya da
LinkedIn. LinkedIn sayfaları herkese açık (misafir) görünümüyle okunur. cv-tools MCP
sunucusunun prepare_job aracı ve poller'ın info-only yolu kullanır.

GÜVENLİK NOTU: kullanıcının LinkedIn oturumunu (linkedin_state.json) bu otomatik tarayıcıya
YÜKLEME. LinkedIn oturum çerezinin başsız/otomatik bir tarayıcıdan geldiğini fark eder,
hesabı işaretler ve kullanıcının BÜTÜN oturumlarını geçersiz kılar (gerçek Chrome'da sürekli
oturum kapanması). LinkedIn otomasyona zaten yalnızca misafir görünümünü sunuyor; yani çerez
hiçbir şey kazandırmıyordu.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


@dataclass
class JobPage:
    """Bir iş ilanı sayfasından okunan yapılandırılmış veri."""

    url: str
    description: str
    title: str = ""
    company: str = ""
    company_url: str = ""
    city: str = ""
    work_type: str = ""   # Full-Time / Part-Time / Contract
    easy_apply: str = ""  # LinkedIn dışı için "Yok"; LinkedIn için "" (tespit edilemiyor)


# Yaygın şehirlerin kanonik yazımı (anahtarlar Türkçe harfleri sadeleştirilmiş + küçük harf;
# yani hem "Eskisehir" hem "Eskişehir" buraya çözülür).
_CITY_MAP = {
    "istanbul": "İstanbul",
    "izmir": "İzmir",
    "ankara": "Ankara",
    "eskisehir": "Eskişehir",
    "bursa": "Bursa",
    "icel": "Mersin",
    "mersin": "Mersin",
}

# Türkçeye özgü harfleri sadeleştir ki yazım farkları aynı anahtara düşsün (uzunluk korunur).
_TR_FOLD = str.maketrans(
    {
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s", "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
        "Ö": "o", "ö": "o", "Ü": "u", "ü": "u",
    }
)


def _city_key(s: str) -> str:
    return s.translate(_TR_FOLD).lower().strip()


# LinkedIn metro bölge etiketleri: 'Greater İzmir', 'İzmir Metropolitan Area', 'İzmir ve
# Çevresi' hepsi şehrin kendisi demek — niteleyiciyi atıp yalın şehre indir.
_AREA_PREFIXES = ("greater ",)
_AREA_SUFFIXES = (
    " metropolitan area",
    " metropolitan bolgesi",
    " ve cevresi",
    " bolgesi",
    " cevresi",
    " area",
)


def _strip_area(s: str) -> str:
    """'Greater İzmir' -> 'İzmir'; 'İzmir Metropolitan Area' -> 'İzmir'."""
    out = (s or "").strip()
    low = _city_key(out)  # uzunluk korunur, yani len() ile dilimleme hizalı kalır
    for p in _AREA_PREFIXES:
        if low.startswith(p):
            out = out[len(p):].strip()
            low = _city_key(out)
            break
    for suf in _AREA_SUFFIXES:
        if low.endswith(suf):
            out = out[: len(out) - len(suf)].strip()
            break
    return out


def _clean_city(text: str) -> str:
    """'Istanbul, Istanbul, Türkiye' gibi bir LinkedIn konumu -> 'İstanbul', ve 'Greater İzmir'
    gibi metro etiketleri -> 'İzmir'.

    Metro bölge niteleyicilerini siler, tekrarlanan parçaları atar, ilkini (şehir) tutar ve
    yazımı kanonikleştirir.
    """
    text = (text or "").strip()
    if not text:
        return ""
    seen: set[str] = set()
    uniq: list[str] = []
    for part in text.split(","):
        p = _strip_area(part.strip())
        k = _city_key(p)
        if k and k not in seen:
            seen.add(k)
            uniq.append(p)
    if not uniq:
        return ""
    return _CITY_MAP.get(_city_key(uniq[0]), uniq[0])


def _map_employment(raw: str) -> str:
    r = (raw or "").strip().lower()
    if not r:
        return ""
    if "part" in r:
        return "Part-Time"
    if "contract" in r or "temporary" in r or "temp" in r:
        return "Contract"
    if "full" in r:
        return "Full-Time"
    return ""

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# LinkedIn'in ilan açıklaması gövdesi için kullandığı seçiciler (girişli ve herkese açık görünüm).
_LINKEDIN_SELECTORS = [
    ".jobs-description__content",
    ".jobs-box__html-content",
    ".show-more-less-html__markup",
    ".description__text",
]

# LinkedIn'de ilan içeriğinin ardından istemediğimiz öneri bölümleri gelir. Bu işaretçilerin
# ilkinden itibaren her şeyi kes.
_LINKEDIN_END_MARKERS = [
    "More jobs",
    "People also viewed",
    "Similar jobs",
    "Jobs you may be interested in",
]


def _truncate_linkedin_noise(text: str) -> str:
    """Drop LinkedIn's trailing 'More jobs' / recommendations sections."""
    low = text.lower()
    cut = len(text)
    for marker in _LINKEDIN_END_MARKERS:
        idx = low.find(marker.lower())
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut].strip()


def _clean_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    # Boş satırları birleştir ve geride kalan çok kısa gezinme parçalarını at.
    cleaned: list[str] = []
    for ln in lines:
        if not ln:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


class Scraper:
    """Keeps one browser/context open across multiple fetches."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "Scraper":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        # Bilerek misafir bağlamı — kullanıcının LinkedIn oturumunu buraya asla bağlama
        # (bkz. modül açıklamasındaki güvenlik notu).
        self._context = self._browser.new_context(user_agent=_USER_AGENT)
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw:
            self._pw.stop()

    def fetch_description(self, url: str) -> str:
        """Geriye dönük uyumlu: sadece açıklama metni."""
        return self.fetch_job(url).description

    def fetch_job(self, url: str) -> JobPage:
        """İlan sayfasını bir kez okur: açıklama + yapılandırılmış alanlar.

        LinkedIn otomasyona yalnızca herkese açık (misafir) görünümünü sunar; yani alanlar herkese
        açık görünümün DOM'undan (üst kart + iş kriterleri listesi) gelir, LinkedIn dışı kariyer
        siteleri için JSON-LD yedeğiyle.
        """
        if not url:
            raise ValueError("Empty job URL")
        is_linkedin = "linkedin.com" in url.lower()
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2_500)
            description = self._extract_description(page, is_linkedin)
            fields = self._extract_fields(page)
            return JobPage(
                url=url,
                description=description,
                title=fields.get("title", ""),
                company=fields.get("company", ""),
                company_url=fields.get("company_url", ""),
                city=fields.get("city", ""),
                work_type=fields.get("work_type", ""),
                easy_apply="" if is_linkedin else "Yok",
            )
        finally:
            page.close()

    def _extract_description(self, page, is_linkedin: bool) -> str:
        if is_linkedin:
            text = self._extract_linkedin(page)
            if text:
                return _truncate_linkedin_noise(text)
            logger.warning("LinkedIn selectors empty; falling back to full-page text.")
        text = _clean_html_to_text(page.content())
        if is_linkedin:
            text = _truncate_linkedin_noise(text)
        if len(text) < 80:
            raise RuntimeError(f"Extracted description too short ({len(text)} chars).")
        return text

    def _extract_fields(self, page) -> dict:
        """LinkedIn herkese açık görünümünden başlık/şirket(+url)/şehir/istihdam türü; JSON-LD
        JobPosting'e düşer (LinkedIn dışı birçok kariyer sitesini kapsar).
        """
        def text_of(sel: str) -> str:
            el = page.query_selector(sel)
            return (el.inner_text() or "").strip() if el else ""

        title = text_of("h1.top-card-layout__title")
        company = company_url = ""
        a = page.query_selector("a.topcard__org-name-link")
        if a:
            company = (a.inner_text() or "").strip()
            company_url = (a.get_attribute("href") or "").split("?", 1)[0]
        city = _clean_city(text_of(".topcard__flavor--bullet"))
        work_type = ""
        for li in page.query_selector_all("li.description__job-criteria-item"):
            t = " ".join((li.inner_text() or "").split())
            if "employment type" in t.lower():
                work_type = _map_employment(t.lower().split("employment type", 1)[-1])
                break

        if not (title and company and city and work_type):
            jl = self._parse_jsonld(page)
            title = title or jl.get("title", "")
            company = company or jl.get("company", "")
            company_url = company_url or jl.get("company_url", "")
            city = city or _clean_city(jl.get("city", ""))
            work_type = work_type or _map_employment(jl.get("employment_type", ""))

        return {"title": title, "company": company, "company_url": company_url,
                "city": city, "work_type": work_type}

    @staticmethod
    def _parse_jsonld(page) -> dict:
        for s in page.query_selector_all('script[type="application/ld+json"]'):
            try:
                data = json.loads(s.inner_text())
            except Exception:  # noqa: BLE001
                continue
            for it in (data if isinstance(data, list) else [data]):
                if not (isinstance(it, dict) and it.get("@type") == "JobPosting"):
                    continue
                org = it.get("hiringOrganization") or {}
                loc = it.get("jobLocation") or {}
                addr = (loc.get("address") if isinstance(loc, dict) else {}) or {}
                emp = it.get("employmentType")
                if isinstance(emp, list):
                    emp = emp[0] if emp else ""
                return {
                    "title": it.get("title", "") or "",
                    "company": org.get("name", "") if isinstance(org, dict) else "",
                    "company_url": (org.get("sameAs") or org.get("url") or "") if isinstance(org, dict) else "",
                    "city": addr.get("addressLocality", "") if isinstance(addr, dict) else "",
                    "employment_type": emp or "",
                }
        return {}

    def _extract_linkedin(self, page) -> str:
        # Varsa "show more"a tıkla ki açıklamanın tamamı DOM'da olsun.
        for sel in (
            "button.show-more-less-html__button",
            "button[aria-label*='more']",
        ):
            try:
                btn = page.query_selector(sel)
                if btn:
                    btn.click(timeout=2_000)
                    page.wait_for_timeout(500)
                    break
            except Exception:  # noqa: BLE001
                pass

        for sel in _LINKEDIN_SELECTORS:
            el = page.query_selector(sel)
            if el:
                html = el.inner_html()
                text = _clean_html_to_text(html)
                if len(text) >= 80:
                    return text
        return ""


def fetch_description(url: str, headless: bool = True) -> str:
    """Tek seferlik kolay okuma (kendi tarayıcısını açıp kapatır)."""
    with Scraper(headless=headless) as s:
        return s.fetch_description(url)
