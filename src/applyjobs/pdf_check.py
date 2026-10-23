"""CV PDF'inin metin katmanı: ATS'nin gerçekte okuduğu şey. Bir düzeltme, bir denetim.

ATS PDF'in görüntüsünü değil metin katmanını okur; görsel olarak kusursuz bir PDF de çöp
çıkarabilir. Örnek projenin (ai-job-search) `tools/verify_pdf.py`'sinin karşılığı, ama bizim en
çok yaşadığımız hataya göre güçlendirilmiş: "incelediğin Markdown ≠ işverene giden PDF" üç kez
canlıya çıktı (docs/mimari-ve-tuzaklar.md). check_cv_output.py Markdown'ı yazım anında denetler;
bu modül son ürünü.

* fix_ligatures(): Google'ın PDF'i Nunito'daki fi/fl'yi tek glif olarak çizer ve metin
  katmanında U+FB01/U+FB02'ye eşler. pdftotext bunu çözer, pypdf gibi basit bir çıkarıcı çözmez:
  "workflows" aranırken "workﬂows" okunur (cv_559'da 9 kelime; 2026-10-23 ölçümü). ToUnicode
  eşlemesi "fi"/"fl"ye çevrilir; çizim değişmez (pdftoppm görüntüsü birebir aynı).
* check_cv_pdf(): iki tür sorun döndürür. `errors` gerçek kusurdur (içerik eşliği, sayfa sayısı,
  okunamayan glif, boyut); `ats` şablondan gelen biçim riskidir (başlığa yapışık alt çizgi,
  Unicode tireli tarih, metin olarak yazılmamış LinkedIn/GitHub). Eski şablon
  (cv_template_eski.docx) `ats` uyarılarını bilerek vermeye devam eder.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from pathlib import Path
from typing import NamedTuple

from pypdf import PdfReader, PdfWriter

from .docx_builder import parse_markdown_cv

# Google'ın her PDF'i için "Object count … exceeds defined trailer size" uyarısı basar: zararsız
# (trailer /Size eksik sayılmış) ve her CV'de agent.log'u kirletirdi.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Greenhouse bu boyutun üstündeki özgeçmişi ayrıştırmaz (resmi yardım sayfası).
MAX_PARSE_BYTES = int(2.5 * 1024 * 1024)
HEADINGS = ("SUMMARY", "CORE SKILLS", "EXPERIENCE", "SELECTED PROJECTS", "EDUCATION")
PREVIOUS_HEADING = "PREVIOUS EXPERIENCE"

_LIGATURES = {chr(c) for c in range(0xFB00, 0xFB07)}  # ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ
_BFRANGE_BLOCK = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
_BFCHAR_BLOCK = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
# Dizi biçimli bir girdi (<lo> <hi> [..]) bütün olarak eşleşir ve olduğu gibi kalır; yoksa
# dizinin içindeki üç <..> yanlışlıkla bir aralık sanılırdı. Düzeltilmiş girdiler de bu biçimde
# olduğu için ikinci bir geçiş hiçbir şeyi değiştirmez.
_BFRANGE = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(?:<([0-9A-Fa-f]+)>|\[[^\]]*\])")
_BFCHAR = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>")

_NON_ASCII_DASHES = "‐‑‒–—―−"
_YEAR = r"(?:19|20)\d{2}"
# Yalnızca yatay boşluk: \s satır sonunu da yakalar ve bir satırın sonundaki yılı sonraki satırın
# başındaki tireye bağlardı (örnek projenin verify_pdf.py'sinde düzeltilen hata).
_NON_ASCII_DATE = re.compile(
    rf"{_YEAR}[^\S\n]*[{_NON_ASCII_DASHES}]|[{_NON_ASCII_DASHES}][^\S\n]*{_YEAR}"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Yalnızca içerik eşliği karşılaştırmasında: ligatürler ayrı bir ATS uyarısı olarak raporlanır,
# burada açılmazsa her "ﬁ"li madde bir de "PDF'te yok" diye ikinci kez sayılırdı.
_FOLDS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "•": " ",
    **{lig: unicodedata.normalize("NFKC", lig) for lig in _LIGATURES},
})


class PdfCheck(NamedTuple):
    errors: list[str]
    ats: list[str]

    def messages(self) -> list[str]:
        return self.errors + [f"ATS: {m}" for m in self.ats]


# --------------------------------------------------------------------------- #
# Ligatür düzeltmesi
# --------------------------------------------------------------------------- #

def _hex_text(text: str) -> bytes:
    return text.encode("utf-16-be").hex().upper().encode()


def _unhex(code: bytes) -> str:
    return bytes.fromhex(code.decode()).decode("utf-16-be", errors="replace")


def _fix_cmap(data: bytes) -> tuple[bytes, int]:
    """ToUnicode CMap'indeki ligatür hedeflerini NFKC açılımına çevirir. (yeni veri, düzeltilen sayı)."""
    fixed = 0

    def range_entry(m: re.Match) -> bytes:
        nonlocal fixed
        lo, hi, dst = m.groups()
        if dst is None:  # dizi biçimi
            return m.group(0)
        base = _unhex(dst)
        if not base:
            return m.group(0)
        dsts = [base[:-1] + chr(ord(base[-1]) + i) for i in range(int(hi, 16) - int(lo, 16) + 1)]
        hits = sum(d[-1] in _LIGATURES for d in dsts)
        if not hits:
            return m.group(0)
        fixed += hits
        # Bir aralık tek bir hedef dizesini artırarak eşler; "fi" artırılamaz, bu yüzden aralık
        # aynı kaynak kodlarıyla dizi biçimine çevrilir (CMap belirtiminde geçerli).
        arr = b" ".join(b"<" + _hex_text(unicodedata.normalize("NFKC", d)) + b">" for d in dsts)
        return b"<" + lo + b"> <" + hi + b"> [" + arr + b"]"

    def char_entry(m: re.Match) -> bytes:
        nonlocal fixed
        src, dst = m.groups()
        text = _unhex(dst)
        if not any(ch in _LIGATURES for ch in text):
            return m.group(0)
        fixed += 1
        return b"<" + src + b"> <" + _hex_text(unicodedata.normalize("NFKC", text)) + b">"

    data = _BFRANGE_BLOCK.sub(
        lambda b: b"beginbfrange" + _BFRANGE.sub(range_entry, b.group(1)) + b"endbfrange", data)
    data = _BFCHAR_BLOCK.sub(
        lambda b: b"beginbfchar" + _BFCHAR.sub(char_entry, b.group(1)) + b"endbfchar", data)
    return data, fixed


def fix_ligatures(pdf_bytes: bytes) -> bytes:
    """Metin katmanındaki ligatür karakterlerini (ﬁ, ﬂ…) düz harflere çevirir.

    Düzeltilecek bir şey yoksa baytlar aynen döner (gereksiz yeniden yazım yok).
    """
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes)))
    fixed = 0
    for page in writer.pages:
        resources = page.get("/Resources")
        fonts = resources.get_object().get("/Font") if resources is not None else None
        if fonts is None:
            continue
        for ref in fonts.get_object().values():
            to_unicode = ref.get_object().get("/ToUnicode")
            if to_unicode is None:
                continue
            stream = to_unicode.get_object()
            data, n = _fix_cmap(stream.get_data())
            if n:
                stream.set_data(data)
                fixed += n
    if not fixed:
        return pdf_bytes
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Denetim
# --------------------------------------------------------------------------- #

def extract_text(pdf_path: Path) -> tuple[str, int]:
    """(metin, sayfa sayısı). Layout modu: varsayılan mod Google'ın PDF'inde her kelimeyi ayrı
    satıra koyuyor ve başlık/satır yapısı kayboluyor."""
    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    return text, len(reader.pages)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_FOLDS)
    return " ".join(text.split())


def _short(text: str) -> str:
    return text if len(text) <= 60 else text[:57] + "..."


def _expected_texts(cv_md: str) -> list[str]:
    """Markdown CV'nin PDF'e birebir gitmesi gereken satırları, build_docx'in yazdığı biçimde."""
    data = parse_markdown_cv(cv_md)
    texts = [data["headline"], data["summary"], data["previous_exp_desc"]]
    for line in data["core_skills"]:
        label, sep, content = line.partition(":")
        texts.append(f"{label.strip()}: {content.strip()}" if sep else line)
    for entry in data["experience"]:
        texts += entry["bullets"]
    for proj in data["projects"]:
        texts += [proj["title"], *proj["bullets"]]
        if proj["tech"]:
            texts.append(f"Tech: {proj['tech']}")
    return [t for t in texts if t and t.strip()]


def check_cv_pdf(pdf_path: Path, cv_md: str) -> PdfCheck:
    """PDF'i Markdown CV'ye ve ATS biçim kurallarına karşı denetler. Boş listeler = temiz."""
    errors: list[str] = []
    ats: list[str] = []
    try:
        text, pages = extract_text(pdf_path)
    except Exception as exc:  # noqa: BLE001 — bozuk PDF bir denetim sonucudur, çökme değil
        return PdfCheck([f"PDF okunamadı: {exc!r}"], [])

    if pages != 1:
        errors.append(f"PDF {pages} sayfa (tek sayfa olmalı)")
    if "(cid:" in text or "�" in text:
        errors.append("metin katmanında okunamayan glif var ((cid:) / �): ATS de aynısını görür")
    if pdf_path.stat().st_size > MAX_PARSE_BYTES:
        errors.append(f"dosya {pdf_path.stat().st_size // 1024} KB: Greenhouse 2.5 MB üstünü ayrıştırmaz")

    flat = _norm(text)
    missing = [t for t in _expected_texts(cv_md) if _norm(t) not in flat]
    if missing:
        listed = "; ".join(repr(_short(m)) for m in missing[:3])
        errors.append(f"Markdown'daki {len(missing)} satır PDF'te yok: {listed}")

    lines = [line.strip() for line in text.splitlines()]
    if any(re.search(r"_{3,}", line) for line in lines):
        ats.append("bölüm başlığına yapışık alt çizgi (____) var: başlık tek token okunur")
    loose = [h for h in HEADINGS if h not in lines]
    if not any(line.startswith(PREVIOUS_HEADING) for line in lines):
        loose.append(PREVIOUS_HEADING)
    if loose:
        ats.append(f"kendi satırında olmayan başlık: {', '.join(loose)}")
    dates = [m.group(0) for m in _NON_ASCII_DATE.finditer(text)]
    if dates:
        ats.append(f"Unicode tireli tarih aralığı (ASCII '-' olmalı): {', '.join(map(repr, dates[:3]))}")
    if not _EMAIL_RE.search(text):
        ats.append("e-posta adresi metin olarak yok")
    for needle in ("linkedin.com/in/", "github.com/"):
        if needle not in text:
            ats.append(f"'{needle}' metin olarak yok (yalnızca link metni ATS'ye URL vermez)")
    ligatures = sorted({ch for ch in text if ch in _LIGATURES})
    if ligatures:
        ats.append(f"metin katmanında ligatür karakteri var ({''.join(ligatures)}): anahtar kelime eşleşmesini bozar")
    return PdfCheck(errors, ats)
