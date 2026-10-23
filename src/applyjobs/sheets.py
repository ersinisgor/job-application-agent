"""Google Drive'daki Excel (.xlsx) dosyasına bir Servis Hesabı ile erişim.

İş listesi Drive'da gerçek bir Excel dosyası olarak tutulur (yerel Google Sheets'e
dönüştürülmez). Dosyayı Drive API ile indirir, openpyxl ile okur/düzenler ve aynı dosya
kimliğinin üzerine yeniden yükleriz. Atanan CV numarası N sütununa geri yazılır.
"""
from __future__ import annotations

import datetime
import fcntl
import functools
import http.client
import io
import logging
import os
import socket
import ssl
import string
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import openpyxl
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from .config import SERVICE_ACCOUNT_FILE, SHEET_LOCK_FILE, settings

logger = logging.getLogger(__name__)

# Servis hesabıyla paylaşılmış, kullanıcıya ait bir dosyayı okumak VE üzerine yazmak için
# Drive kapsamı gerekir.
SCOPES = ["https://www.googleapis.com/auth/drive"]

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# İlgilendiğimiz sütun harfleri (A..Q). Bu listedeki indeks, satır değerine karşılık gelir.
COLUMNS = list(string.ascii_uppercase[:17])  # A..Q

# Doğrudan kullandığımız sütunlar için okunaklı takma adlar.
COL_BASVURU = "B"
COL_CITY = "F"       # Yer
COL_WORK_MODE = "G"  # Uzaktan: Hybrit / On-site / Remote
COL_COMPANY = "J"
COL_LINK = "K"
COL_POZISYON = "L"
COL_ILAN_NO = "M"
COL_CV_NO = "N"
COL_MATCH_RATE = "P"  # post-optimization ATS Match Rate
COL_LANGUAGES = "Q"   # job's top two priority programming languages ("Python, Java")

# openpyxl için 1 tabanlı sütun indeksleri.
CV_NO_COL_INDEX = COLUMNS.index(COL_CV_NO) + 1        # = 14
MATCH_RATE_COL_INDEX = COLUMNS.index(COL_MATCH_RATE) + 1  # = 16
LANGUAGES_COL_INDEX = COLUMNS.index(COL_LANGUAGES) + 1    # = 17

# Diller hücresinin (Q) yazı boyutu (punto) — kullanıcı küçük istiyor (7pt).
LANGUAGES_FONT_SIZE = 7

# Dropdown'ların uygulanacağı son veri satırı (sheet'in sabit 1000 satırlık ızgarası var).
DROPDOWN_LAST_ROW = 1000

# Kullanıcının bu sütunlarda tuttuğu dropdown'lar (veri doğrulamaları). openpyxl dosyayı
# yeniden kaydederken veri doğrulamalarını düşürür; bu yüzden kullanıcının elle giriş
# dropdown'ları bozulmasın diye her yazımda yeniden uygularız.
DROPDOWNS: dict[str, list[str]] = {
    # Başvuru. "Üretilecek" CV tetiğidir (config.CV_TRIGGER_BASVURU_VALUES) ve tek tık uzakta olsun
    # diye ilk sırada; geri kalanlar sheet'te gerçekten kullanılan değerler. Bu liste sheet'in
    # dropdown'ının TA KENDİSİDİR — _apply_dropdowns her yazımda doğrulamaları bundan yeniden kurar,
    # yani burada olmayan her şey sheet'in kendi dropdown'ından kaybolur.
    "B": ["Üretilecek", "Olabilir", "Başvurulmuş", "✓", "Geçmiş", "Vazgeçildi"],
    "C": ["Var", "Yok"],                              # Easy Apply
    "G": ["Hybrit", "On-site", "Remote"],            # Uzaktan
    "H": ["Full-Time", "Part-Time", "Contract"],     # Çalışma Şekli
}


class SheetLockTimeout(RuntimeError):
    """Başka bir süreç sheet kilidini zaman aşımından uzun süre tuttu."""


_LOCK_TIMEOUT = 120.0  # bir indir-düzenle-yükle ~2-6 sn; 120 sn bir şeylerin ters gittiği anlamına gelir
_LOCK_POLL = 0.25


@contextmanager
def sheet_lock(timeout: float = _LOCK_TIMEOUT):
    """Bütün bir indir -> openpyxl ile düzenle -> yükle döngüsünü SÜREÇLER arasında sıraya koyar.

    Birden çok yazar var: CV agent'ının MCP sunucusu (write_processed_row), poller'ın info-only
    yolu ve özet API'si (/add-job -> append_job_rows, sen LinkedIn'de gezinirken). Her biri
    dosyayı yeniden indirir, bellekte düzenler ve çalışma kitabının TAMAMINI yeniden yükler;
    yani bu kilit olmasa, bir CV yazımı bitmeden başlamış bir satır ekleme o CV No'yu içermeyen
    bir çalışma kitabı yüklerdi — CV No'yu sessizce geri alır ve CV bir sonraki taramada yeniden
    üretilirdi.

    state/sheet.lock üzerinde danışma flock'u; bloklamayan + yeniden deneme, böylece bir panel
    isteğini sonsuza kadar asmak yerine zaman aşımına uğrayabiliriz.

    Yeniden girişli DEĞİL: aynı dosyanın ikinci bir açık dosya tanımı üzerindeki flock, tek bir
    süreç içinde bile bloklar. Bir @_locked metodu asla başka birinin içinden çağırma.
    """
    SHEET_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(SHEET_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise SheetLockTimeout(
                        f"Sheet is being written by another process "
                        f"(waited {timeout:.0f}s)."
                    )
                time.sleep(_LOCK_POLL)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _locked(method):
    """Sheet'i değiştiren bir SheetsClient metodunu süreçler arası sheet kilidiyle sarar."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with sheet_lock():
            return method(self, *args, **kwargs)

    return wrapper


def _apply_dropdowns(ws) -> None:
    """Kullanıcının sütun dropdown'larını openpyxl gidiş-dönüşünden sağ çıksınlar diye (yeniden) kurar."""
    ws.data_validations.dataValidation.clear()
    for col, options in DROPDOWNS.items():
        # Inline list validation: values joined by commas inside double quotes.
        formula = '"' + ",".join(options) + '"'
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
        dv.add(f"{col}2:{col}{DROPDOWN_LAST_ROW}")
        ws.add_data_validation(dv)


@dataclass
class Row:
    """Tek bir sheet satırı (1 tabanlı sheet satır numarası)."""

    number: int  # gerçek sheet satır numarası (başlık 1. satır, veri 2'den başlar)
    cells: dict[str, str] = field(default_factory=dict)  # sütun harfi -> değer

    def get(self, col: str) -> str:
        return self.cells.get(col, "").strip()

    @property
    def link(self) -> str:
        return self.get(COL_LINK)

    @property
    def basvuru(self) -> str:
        return self.get(COL_BASVURU)

    @property
    def city(self) -> str:
        return self.get(COL_CITY)

    @property
    def work_mode(self) -> str:
        return self.get(COL_WORK_MODE)

    @property
    def cv_no(self) -> str:
        return self.get(COL_CV_NO)

    @property
    def ilan_no(self) -> str:
        return self.get(COL_ILAN_NO)

    def key(self) -> str:
        """Çalışmalar arasında tekrar kontrolü için sabit tanımlayıcı.

        Satır numarası + değişken sorgu kısmı atılmış link üzerine kurulu. M sütunundan
        (İlan Numarası) kaçınırız çünkü o bir sheet formülü. Yeniden işlemeye karşı asıl koruma
        zaten N sütununa yazılan CV No'dur.
        """
        base_link = self.link.split("?", 1)[0]
        return f"row:{self.number}:{base_link}"


def _cell_to_str(value) -> str:
    if value is None:
        return ""
    return str(value)


def _link_font(cell) -> Font:
    """10 puntoda köprü stili (mavi, altı çizili); hücrenin yazı tipi ailesi korunur."""
    return Font(name=cell.font.name, size=10, color="1155CC", underline="single")


def _languages_font(cell) -> Font:
    """Diller hücresi (Q) için küçük (7pt) düz yazı tipi; hücrenin yazı tipi ailesi korunur."""
    return Font(name=cell.font.name, size=LANGUAGES_FONT_SIZE)


# Başarısız bir istek değil, ölü bir TCP bağlantısı. Özet API'si uzun ömürlü, çoğunlukla boşta
# duran bir süreç: Google havuzdaki keep-alive bağlantısını birkaç dakika sonra kapatır ve
# sonraki Drive çağrısı kimsenin dinlemediği bir sokete yazar (BrokenPipeError [Errno 32], ya
# da reset / SSL EOF / "Remote end closed"). httplib2 yalnızca ENETUNREACH ve EADDRNOTAVAIL'i
# kendiliğinden yeniden dener; bu yüzden sessiz bir aradan sonraki ilk tıklama panele 500 olarak
# ulaşıyordu.
_STALE_CONN_ERRORS = (
    ConnectionError,  # BrokenPipe / ConnectionReset / ConnectionAborted
    TimeoutError,  # socket.timeout since 3.10
    socket.gaierror,  # geçici DNS hatası (ör. dizüstü bilgisayar yeni uyandı)
    ssl.SSLError,  # includes SSLEOFError
    http.client.HTTPException,  # RemoteDisconnected, CannotSendRequest, BadStatusLine
)
_DRIVE_ATTEMPTS = 3
_DRIVE_RETRY_SLEEP = 1.0  # saniye, deneme numarasıyla çarpılır


class SheetsClient:
    """.xlsx iş listesi için Drive destekli okuyucu/yazıcı."""

    def __init__(self) -> None:
        creds = Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
        )
        self._drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._file_id = settings.spreadsheet_id

    # --- Drive download / upload -------------------------------------------------

    def _drop_stale_connections(self) -> None:
        """Havuzdaki TCP bağlantılarını atar ki sonraki çağrı yeni bir bağlantı açsın.

        httplib2 her host için bir bağlantıyı önbellekte tutar ve bir yazım EPIPE ile başarısız
        olduğunda onu KAPATMAZ; yani düz bir yeniden deneme aynı ölü soketi yeniden kullanırdı.
        """
        transport = getattr(self._drive, "_http", None)
        # google_auth_httplib2.AuthorizedHttp gerçek httplib2.Http'yi .http içinde sarar
        inner = getattr(transport, "http", transport)
        connections = getattr(inner, "connections", None)
        if not connections:
            return
        for conn in list(connections.values()):
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - closing a dead socket may fail; ignore
                pass
        connections.clear()

    def _retry_drive(self, what: str, call):
        """Bir Drive çağrısını çalıştırır; havuzdaki bağlantı bayatladıysa bir kez yeniden bağlanır.

        Yalnızca bağlantı düzeyindeki hatalar yeniden denenir; bir HTTP hatası (404, 403, kota)
        Google'dan gelen gerçek bir cevaptır ve değişmeden yüzeye çıkmalıdır. Buradaki iki çağrı için
        de yeniden denemek güvenli: indirme bir okuma, yükleme ise bu süreç sheet kilidini tutarken
        çalışma kitabının tamamını aynı baytlarla değiştirir.
        """
        for attempt in range(1, _DRIVE_ATTEMPTS + 1):
            try:
                return call()
            except _STALE_CONN_ERRORS as exc:
                if attempt == _DRIVE_ATTEMPTS:
                    raise
                logger.warning(
                    "Drive %s failed (%s: %s); reconnecting, attempt %d/%d",
                    what,
                    type(exc).__name__,
                    exc,
                    attempt + 1,
                    _DRIVE_ATTEMPTS,
                )
                self._drop_stale_connections()
                time.sleep(_DRIVE_RETRY_SLEEP * attempt)

    def _download_bytes(self) -> bytes:
        def once() -> bytes:
            # Her denemede yeniden kurulur: başarısız denemeden kalan yarı dolu bir tampon, yeniden
            # denemenin baytlarının önüne eklenmemeli.
            request = self._drive.files().get_media(fileId=self._file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            return buf.read()

        return self._retry_drive("download", once)

    def _load_workbook(self):
        data = self._download_bytes()
        wb = openpyxl.load_workbook(io.BytesIO(data))
        if settings.sheet_name in wb.sheetnames:
            ws = wb[settings.sheet_name]
        else:
            ws = wb.active
        return wb, ws

    def _upload(self, wb) -> None:
        buf = io.BytesIO()
        wb.save(buf)  # bir kez serileştir; yalnızca aktarım yeniden denenir
        data = buf.getvalue()

        def once() -> None:
            # Her denemede yeni bir akış + medya nesnesi: MediaIoBaseUpload kendi okuma konumunu tutar,
            # yani onu yeniden kullanmak kesilmiş bir çalışma kitabı yüklerdi.
            media = MediaIoBaseUpload(
                io.BytesIO(data), mimetype=XLSX_MIME, resumable=True
            )
            self._drive.files().update(
                fileId=self._file_id, media_body=media
            ).execute()

        self._retry_drive("upload", once)

    # --- Public API (same surface as before) -------------------------------------

    def get_rows(self) -> list[Row]:
        """Boş olmayan bütün veri satırlarını döndürür (sheet'in 2. satırından itibaren)."""
        _, ws = self._load_workbook()
        rows: list[Row] = []
        for r in range(2, ws.max_row + 1):
            cells: dict[str, str] = {}
            non_empty = False
            for j, col in enumerate(COLUMNS):
                val = _cell_to_str(ws.cell(row=r, column=j + 1).value)
                cells[col] = val
                if val.strip():
                    non_empty = True
            if non_empty:
                rows.append(Row(number=r, cells=cells))
        return rows

    @staticmethod
    def _as_int(val: str) -> int | None:
        val = val.strip()
        if not val:
            return None
        try:
            return int(float(val))  # "200" ve "200.0" değerlerini tolere eder
        except ValueError:
            return None

    def next_cv_number(self, rows: list[Row]) -> int:
        """N sütunundaki (CV No) en yüksek sayısal değer + 1, en az 1."""
        nums = [n for r in rows if (n := self._as_int(r.cv_no)) is not None]
        return (max(nums) + 1) if nums else 1

    @_locked
    def write_cv_number(self, row_number: int, cv_no: int) -> None:
        """En son dosyayı yeniden indirir, N{row}'u ayarlar ve yeniden yükler.

        Yazmadan hemen önce taze indirmek üzerine yazma penceresini çok küçük tutar; böylece
        dosyanın başka yerinde yaptığın düzenlemeleri ezmeyiz.
        """
        wb, ws = self._load_workbook()
        ws.cell(row=row_number, column=CV_NO_COL_INDEX).value = cv_no
        _apply_dropdowns(ws)
        self._upload(wb)

    @_locked
    def write_match_rate(self, row_number: int, match_rate: float) -> None:
        """Optimizasyon sonrası ATS Eşleşme Oranını P sütununa yazar."""
        wb, ws = self._load_workbook()
        ws.cell(row=row_number, column=MATCH_RATE_COL_INDEX).value = match_rate
        _apply_dropdowns(ws)
        self._upload(wb)

    @_locked
    def write_cv_and_match(
        self, row_number: int, cv_no: int, match_rate: float | None = None
    ) -> None:
        """CV No'yu (N) ve varsa Eşleşme Oranını (P) tek bir yüklemede yazar.

        İkisini tek bir indir-düzenle-yükle döngüsünde yapmak dosyanın ne sıklıkla (ve ne kadar
        süre) değiştirildiğini en aza indirir; aynı anda tarayıcıda yaptığın düzenlemeleri ezme
        olasılığını azaltır.
        """
        wb, ws = self._load_workbook()
        ws.cell(row=row_number, column=CV_NO_COL_INDEX).value = cv_no
        if match_rate is not None:
            ws.cell(row=row_number, column=MATCH_RATE_COL_INDEX).value = match_rate
        _apply_dropdowns(ws)
        self._upload(wb)

    # --- New-row append (Huntr import) -------------------------------------------

    @staticmethod
    def _col(letter: str) -> int:
        return COLUMNS.index(letter) + 1

    def _last_data_row(self, ws) -> int:
        """Herhangi bir anahtar sütunda (A/J/K/L/N) veri olan en yüksek satır."""
        key_cols = [self._col(c) for c in ("A", "J", "K", "L", "N")]
        last = 1
        for r in range(2, ws.max_row + 1):
            if any(_cell_to_str(ws.cell(row=r, column=c).value).strip() for c in key_cols):
                last = r
        return last

    def _set_link_cell(self, cell, url: str) -> None:
        """Tıklanabilir bir köprü hücresi yazar (mavi, altı çizili)."""
        cell.value = url
        if url:
            cell.hyperlink = url
            cell.font = _link_font(cell)

    @_locked
    def append_job_rows(self, jobs: list[dict], cv_no_marker: str | None = None) -> list[int]:
        """Yeni ilanlar için satır ekler — K (link) + E (tarih) + A (No) + I + M yazar.

        Her ilan sözlüğünde en az {"url": ...} olmalı. Huntr kaynaklı bilgi de ("company"/"title"/
        "city") TAŞIYABİLİR; bu hemen J/L/F'ye yazılır — info-only (CV_GENERATION kapalı) yolu
        bunu kullanır, böylece sheet (çoğu zaman süresi geçmiş) ilan sayfasını yeniden okumak
        yerine doğrudan Huntr'dan doldurulur. cv_no_marker verilirse N'ye (CV No) yazılır, böylece
        satır CV'siz işlenmiş sayılır.

        CV üretim modunda çağıran yalnızca url içeren sözlükler geçirir ve işaretçi vermez; kalan
        sütunlar (C/F/H/J/L) daha sonra okunan sayfadan write_processed_row ile doldurulur — eskisi
        gibi. Tek indir-düzenle-yükle.
        """
        if not jobs:
            return []
        wb, ws = self._load_workbook()
        last = self._last_data_row(ws)
        date_fmt = ws.cell(row=last, column=self._col("E")).number_format if last >= 2 else None
        # "No" (A) numaralandırmasını yukarıdaki en son sayısal değerden sürdür.
        last_a = None
        for rr in range(last, 1, -1):
            v = self._as_int(_cell_to_str(ws.cell(row=rr, column=self._col("A")).value))
            if v is not None:
                last_a = v
                break
        today = datetime.datetime(*datetime.date.today().timetuple()[:3])

        written: list[int] = []
        r = last + 1
        for job in jobs:
            if last_a is not None:
                last_a += 1
                ws.cell(row=r, column=self._col("A")).value = last_a
            e_cell = ws.cell(row=r, column=self._col("E"))
            e_cell.value = today
            if date_fmt:
                e_cell.number_format = date_fmt
            ws.cell(row=r, column=self._col("I")).value = "İş"
            self._set_link_cell(ws.cell(row=r, column=self._col("K")), job.get("url", ""))
            # İlan No formülü: "/jobs/view/" ile sonraki "/" arasındaki no'yu çıkarır.
            ws.cell(row=r, column=self._col("M")).value = (
                f'=IFERROR(MID(K{r},FIND("/jobs/view/",K{r})+11,'
                f'FIND("/",K{r}&"/",FIND("/jobs/view/",K{r})+11)-FIND("/jobs/view/",K{r})-11),"")'
            )
            # İsteğe bağlı Huntr kaynaklı bilgi (info-only yolu); yalnızca verildiyse yazılır.
            if job.get("company"):
                ws.cell(row=r, column=self._col("J")).value = job["company"]
            if job.get("title"):
                ws.cell(row=r, column=self._col("L")).value = job["title"]
            if job.get("city"):
                ws.cell(row=r, column=self._col("F")).value = job["city"]
            if cv_no_marker is not None:
                ws.cell(row=r, column=CV_NO_COL_INDEX).value = cv_no_marker
            written.append(r)
            r += 1

        _apply_dropdowns(ws)
        self._upload(wb)
        return written

    def _fill_page_fields(self, ws, row_number: int, fields: dict) -> None:
        """YALNIZCA BOŞ olan C/F/H/J/L'yi okunan sayfadan doldurur (J şirket köprüsü olarak).
        G'ye asla dokunulmaz (elle doldurulur). Yükleme yapmaz.
        """

        def fill(col: str, val: str):
            if not val:
                return None
            cell = ws.cell(row=row_number, column=self._col(col))
            if _cell_to_str(cell.value).strip() == "":
                cell.value = val
                return cell
            return None

        fill("C", fields.get("C", ""))   # Easy Apply (only set for non-LinkedIn = "Yok")
        fill("F", fields.get("F", ""))   # city
        fill("H", fields.get("H", ""))   # istihdam türü
        fill("L", fields.get("L", ""))   # title
        fill("J", fields.get("J", ""))   # şirket

        # Şirket KÖPRÜSÜ, scrape bir tane bulduğunda ve hücrede zaten yoksa uygulanır — metni az önce
        # bizim yazmış olmamıza bilerek BAĞLANMAZ. Panelin "Ekle" butonu J'yi satır eklerken doldurur
        # (düz metin, şirket URL'si yok); yani yalnızca-boşsa kuralı adı sonsuza kadar tıklanamaz
        # bırakırdı: scrape company_url'yi döndürdüğünde hücre artık boş değildir.
        j_cell = ws.cell(row=row_number, column=self._col("J"))
        if fields.get("J_url") and not j_cell.hyperlink and _cell_to_str(j_cell.value).strip():
            j_cell.hyperlink = fields["J_url"]
            j_cell.font = _link_font(j_cell)

    def _set_languages_cell(self, cell, languages: str) -> None:
        """İlanın öncelikli dillerini ("Python, Java") Q'ya 7pt olarak yazar.
        Yalnızca boş değilse değer yazar (ilan dili yoksa hücre boş kalır).
        """
        if not languages:
            return
        cell.value = languages
        cell.font = _languages_font(cell)

    @_locked
    def write_processed_row(
        self,
        row_number: int,
        fields: dict,
        cv_no: int,
        match_rate: float | None = None,
        languages: str = "",
    ) -> None:
        """YALNIZCA BOŞ olan C/F/H/J/L'yi okunan sayfadan doldurur (J şirket köprüsü olarak), artı
        N (CV No), P (Eşleşme Oranı) ve Q (öncelikli programlama dilleri, 7pt). G'ye asla
        dokunulmaz (elle doldurulur). Tek indir-düzenle-yükle.
        """
        wb, ws = self._load_workbook()
        self._fill_page_fields(ws, row_number, fields)
        ws.cell(row=row_number, column=CV_NO_COL_INDEX).value = cv_no
        if match_rate is not None:
            ws.cell(row=row_number, column=MATCH_RATE_COL_INDEX).value = match_rate
        self._set_languages_cell(
            ws.cell(row=row_number, column=LANGUAGES_COL_INDEX), languages
        )
        _apply_dropdowns(ws)
        self._upload(wb)

    @_locked
    def write_info_only_row(self, row_number: int, fields: dict, cv_no_marker: str) -> None:
        """CV üretimi KAPALI yolu: YALNIZCA BOŞ olan C/F/H/J/L'yi okunan sayfadan doldurur ve N'ye
        sayısal olmayan bir işaretçi (ör. "Yok") yazar; satır işlenmiş sayılır ama ona asla CV
        atanmaz. Eşleşme Oranı yazılmaz. Tek indir-düzenle-yükle.
        """
        wb, ws = self._load_workbook()
        self._fill_page_fields(ws, row_number, fields)
        ws.cell(row=row_number, column=CV_NO_COL_INDEX).value = cv_no_marker
        _apply_dropdowns(ws)
        self._upload(wb)
