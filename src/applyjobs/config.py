"""Merkezi yapılandırma: .env'i yükler ve proje yollarını çözer.

Diğer bütün modüller `settings`'i buradan import eder.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Proje kökü = bu dosyanın iki üst klasörü (src/applyjobs/config.py -> proje kökü)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

# Adayın gerçekleri (CV + projeler): her agent'ın okuduğu tek gerçek kaynak.
PROFILE_DIR = PROJECT_ROOT / "profile"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
# Doğrudan API ile çağrılan tek model işinin (panel özeti) Türkçe system prompt'u.
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SUMMARY_PROMPT_FILE = PROMPTS_DIR / "ozet_sistem.md"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
STATE_DIR = PROJECT_ROOT / "state"
# Üretilen CV'ler, analizler, ilan metinleri ve mektuplar (gitignore'da).
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Yapılandırma dosyaları
CV_BASE_FILE = PROFILE_DIR / "cv_base.md"
PROJECTS_LIST_FILE = PROFILE_DIR / "projects.md"

# Yapılandırma dosyası: Google Docs çıktısı için .docx şablonu
CV_TEMPLATE_FILE = TEMPLATES_DIR / "cv_template.docx"

# Kimlik bilgisi dosyaları
SERVICE_ACCOUNT_FILE = CREDENTIALS_DIR / "service_account.json"
LINKEDIN_STATE_FILE = CREDENTIALS_DIR / "linkedin_state.json"
# Huntr girişi Google SSO arkasında; bu da otomatik tarayıcıları engelliyor. Bu yüzden
# bir storage_state dosyası yerine kalıcı, gerçek bir Chrome profili kullanıyoruz: oturum
# kalıcı olur ve Google'ın "tarayıcı güvenli değil" engeli aşılmış olur.
HUNTR_PROFILE_DIR = CREDENTIALS_DIR / "huntr_profile"
# Drive'da Google Doc oluşturmak için OAuth (kullanıcı) kimlik bilgileri
OAUTH_CLIENT_FILE = CREDENTIALS_DIR / "oauth_client.json"
OAUTH_TOKEN_FILE = CREDENTIALS_DIR / "oauth_token.json"

# Durum dosyaları
PROCESSED_STATE_FILE = STATE_DIR / "processed.json"
# Daha önce işlenmiş Huntr board ilan anahtarları (başlangıç + işlenenler). Eski createdAt
# imlecinin yerini aldı; o güvenilir değildi (createdAt her zaman kaydetme zamanı değil).
HUNTR_SEEN_FILE = STATE_DIR / "huntr_seen.json"
# Eski: en yüksek Huntr createdAt (artık kullanılmıyor; eski dosyalar zararsız kalsın diye duruyor).
HUNTR_CURSOR_FILE = STATE_DIR / "huntr_cursor.txt"
# Extension API'sinin özet önbelleği, LinkedIn ilan no'suna göre anahtarlı: bir ilan bir kez
# özetlenir ve API yeniden başlasa da kalır.
SUMMARY_CACHE_FILE = STATE_DIR / "summary_cache.json"

# Panelin "Ekle" butonunun kaydettiği ilan metinleri, LinkedIn ilan no'suna göre anahtarlı.
# Misafir görünümlü scrape BİRİNCİL kaynak olarak kalır; bu metin yalnızca o scrape başarısız
# olursa (ve --allow-staged istenirse) okunur, böylece CV kullanıcının panelde gördüğü metinden
# yine de üretilebilir.
PENDING_JD_DIR = STATE_DIR / "pending_jd"
# Bunun altındaki metin bir ilan değildir (yarım yüklenmiş bir parça) ve ona dayanan bir CV
# hiç CV olmamasından kötüdür. Bilerek scraper'ın 80 karakterlik tabanının üstünde.
PENDING_JD_MIN_CHARS = 200
# Kaydedilen dosyalar CV'leri yazılınca silinir; bundan eski olan her şey çöptür (elle silinmiş
# satır, kapalı CV üretimi, başarısız bir satır ekleme).
PENDING_JD_MAX_AGE_DAYS = 14

# .xlsx'in indir -> düzenle -> yükle döngüsünün tamamını koruyan danışma kilidi. Dosyaya artık
# birden çok süreç yazıyor: CV agent'ının MCP sunucusu, poller ve özet API'si (panelin "Ekle" butonu).
SHEET_LOCK_FILE = STATE_DIR / "sheet.lock"

# "Başvuru" (B) sütununda CV üretimini TETİKLEYEN değerler. Bilerek bir izin listesi: ilan ilginç
# göründüğü an satır sheet'e eklenir, ama başvuru çoğu zaman günler sonra yapılır ve o zamana kadar
# ilan kalkmış olabilir — yani ekleme anında üretilen CV çoğu kez hiç başvurulmayan bir işin CV'si
# olur. Kullanıcı gerçekten başvururken satırı "Üretilecek" yapar ve CV ancak o zaman üretilir.
# Bunu sheets.DROPDOWNS["B"] ile senkron tut; sheet'in dropdown'ı gerçekte onu sunar.
CV_TRIGGER_BASVURU_VALUES = {"Üretilecek"}

# CV üretimi KAPALIYKEN içe aktarılan satırlar için CV No sütununa (N) yazılan işaretçi. Sayısal
# değil; bu yüzden CV numaralandırmasında yok sayılır ama yine de "yapıldı" sayılır — satır okunan
# bilgisini korur ama ona asla (yeniden) CV atanmaz. Satırı yeniden CV'ye uygun yapmak için elle sil.
NO_CV_MARKER = "Yok"

# İşaretli bir satırın ilanı artık okunamıyorsa N'ye yazılan işaretçi. CV üretilmez ve CV numarası
# harcanmaz: ertelenmiş tetiğin bütün amacı kalkmış bir ilana üretim harcamamak. Tekrar denemek için N'yi
# temizle ve B'yi yeniden işaretle (scrape LinkedIn tarafındaki nedenlerle de başarısız olabilir), ya da
# panelin kaydettiği metinle zorla üret: `run_once.py --row N --allow-staged`.
EXPIRED_MARKER = "Kalkmış"


def _expand(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str)).resolve()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "on", "yes", "evet", "açık")


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    # CV agent'larının (cv-writer / cv-reviewer) modeli ve effort'u. claude -p'ye
    # --model / --effort olarak geçer. Eski CLAUDE_MODEL / CLAUDE_EFFORT yerine yeni ad:
    # Claude Code kendi CLAUDE_EFFORT değişkenini her Bash komutuna ihraç ediyor ve
    # load_dotenv var olanı ezmediği için .env'deki değer sessizce yok sayılıyordu.
    cv_model: str
    cv_effort: str
    # claude CLI'nin yolu. Boşsa PATH'te, sonra ~/.local/bin/claude'da aranır (Finder'dan
    # çift tıklanan .command dosyalarında PATH dar olur).
    claude_bin: str
    # LinkedIn İlan Özeti API'sinin modeli (CV agent'larının cv_model'inden ayrı). Hızlı ve
    # ucuz özetler için varsayılan Haiku.
    summary_model: str
    # İstendiğinde üretilen mektupların modeli (yine ayrı: mektup kısa bir düzyazı; ne CV'nin
    # düşünme bütçesine ne de özetin Haiku'suna ihtiyaç duyar).
    cover_letter_model: str
    cv_review: bool
    cv_generation: bool
    spreadsheet_id: str
    sheet_name: str
    poll_interval: int
    output_dir: Path
    analysis_dir: Path
    job_description_dir: Path
    cover_letter_dir: Path
    resumes_folder_name: str
    resumes_folder_id: str
    huntr_board_url: str
    huntr_poll_interval: int

    @classmethod
    def load(cls) -> "Settings":
        # Üretilen her dosya proje içinde, outputs/ altında durur (gitignore'da).
        default_output = str(OUTPUTS_DIR / "cv")
        default_analysis = str(OUTPUTS_DIR / "cv" / "analysis")
        default_jd = str(OUTPUTS_DIR / "job_descriptions")
        # El yapımı eski mektuplarla aynı klasörü paylaşır (cover_letter_<no>_<be|fs>.docx, No. 138'e
        # kadar). Yeni dosyalar cover_letter_<no>_<lang>.md — farklı ek ve uzantı, birlikte durabilirler.
        # Bir mektubu bulmak için bu klasörde asla glob yapma.
        default_cover = str(OUTPUTS_DIR / "cover_letters")
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            cv_model=os.getenv("CV_MODEL", "claude-sonnet-5"),
            # low / medium / high / xhigh / max. medium, ölçülmüş en iyi denge (bkz. KULLANIM.md).
            cv_effort=os.getenv("CV_EFFORT", "medium").strip().lower(),
            claude_bin=os.getenv("CLAUDE_BIN", "").strip(),
            # LinkedIn İlan Özeti API'sinin (extension) modeli. Varsayılan Haiku.
            summary_model=os.getenv("SUMMARY_MODEL", "claude-haiku-4-5"),
            # Mektuplar: cover-letter-writer agent'ı bu modelle, düşük effort ile çalışır.
            cover_letter_model=os.getenv("COVER_LETTER_MODEL", "claude-sonnet-5"),
            # Her CV'ye ikinci bir uzman QA geçişi (cv-reviewer agent'ı). Varsayılan KAPALI: doğrula/düzelt
            # kontrol listesi zaten tek üretim geçişinin içinde (ats-cv-kurallari, ADIM 12).
            cv_review=_env_bool("CV_REVIEW", False),
            # CV üretiminin ana anahtarı. AÇIK (varsayılan): işaretli satırlara tam CV + sheet bilgisi.
            # KAPALI: satırlar yine işlenir ve sayfa bilgisi sheet'e yazılır, ama CV ÜRETİLMEZ (N sütununa
            # "Yok" işaretçisi yazılır, böylece anahtar yeniden açılınca satır geriye dönük üretilmez).
            cv_generation=_env_bool("CV_GENERATION", True),
            spreadsheet_id=os.getenv("SPREADSHEET_ID", ""),
            sheet_name=os.getenv("SHEET_NAME", "Sayfa1"),
            poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
            output_dir=_expand(os.getenv("OUTPUT_DIR", default_output)),
            analysis_dir=_expand(os.getenv("ANALYSIS_DIR", default_analysis)),
            job_description_dir=_expand(os.getenv("JOB_DESCRIPTION_DIR", default_jd)),
            cover_letter_dir=_expand(os.getenv("COVER_LETTER_DIR", default_cover)),
            resumes_folder_name=os.getenv("RESUMES_FOLDER_NAME", "Resumes Based on Jobs"),
            resumes_folder_id=os.getenv("RESUMES_FOLDER_ID", ""),
            # Board URL'si verilmedikçe Huntr KAPALI (özellik bayrağı).
            huntr_board_url=os.getenv("HUNTR_BOARD_URL", ""),
            huntr_poll_interval=int(os.getenv("HUNTR_POLL_INTERVAL", "30")),
        )

    @property
    def markdown_dir(self) -> Path:
        """Markdown CV'lerin durduğu yer (CV çıktı klasörünün alt klasörü)."""
        return self.output_dir / "markdown"

    @property
    def pdf_dir(self) -> Path:
        """Google Doc'lardan dışa aktarılan CV PDF'lerinin indirildiği yer."""
        return self.output_dir / "pdf"

    def validate(self) -> None:
        # ANTHROPIC_API_KEY burada aranmıyor: CV ve mektup artık Claude Code agent'larıyla
        # (abonelik girişiyle) üretiliyor. Anahtar sadece panel özeti için summary_api'de lazım.
        missing = []
        if not self.spreadsheet_id:
            missing.append("SPREADSHEET_ID")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )
        if not SERVICE_ACCOUNT_FILE.exists():
            raise RuntimeError(
                f"Service account key not found at {SERVICE_ACCOUNT_FILE}. "
                f"Create one in Google Cloud and share the sheet with its email."
            )

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.job_description_dir.mkdir(parents=True, exist_ok=True)
        self.cover_letter_dir.mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_JD_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings.load()
