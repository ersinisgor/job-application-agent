# job-apply-agent

Drive'daki iş-başvuru listenizi izleyen ve **siz işaretlediğiniz** ilanlar için o ilana özel,
ATS-optimize **İngilizce CV** üreten bir agent.

İşaretlenen her satır için:

1. **K (İlan Linki)** sütunundaki linke gider ve ilan açıklamasını okur (Playwright;
   LinkedIn dahil firma kendi siteleri de desteklenir). İlan yayından kalkmışsa CV üretmez,
   satırı `Kalkmış` işaretleyip geçer.
2. ATS CV Optimization talimatına göre CV üretir (`config/ats_prompt.md`).
3. CV'yi `cv_<no>.md` olarak `~/Desktop/İş Arama/Job Applications/2026/CVs/` altına kaydeder ve
   `config/cv_template.docx` şablonundan Google Doc + PDF çıkarır.
4. Tabloya **tek seferde** yazar: **N (CV No)**, **P (Match Rate)**, **Q (Yazılım Dili)** ve
   sayfadan okunan boş hücreler (F/H/J/L/C).

## Tetikleme kuralı

Bir satır şu durumda işlenir: **K (link) dolu**, **N (CV No) boş** ve **B (Başvuru) = `Üretilecek`**.

CV üretimi ilanı eklerken değil, **başvurmaya karar verdiğinde** olur. Sebebi: eklenen ilana
çoğu zaman aynı gün başvurulamıyor, sıra geldiğinde ilan kalkmış oluyor ve hiç başvurulmayacak
ilanlara CV üretilmiş oluyordu. Akış:

1. İlandayken panelin **Ekle** butonu → satır (link + pozisyon + firma) tabloya düşer, B boş kalır.
2. Başvuracağın gün → o satırın **B** sütununu dropdown'dan `Üretilecek` yap.
3. Üret → `scripts/cv_uret.command` dosyasına çift tıkla (ya da poller açıksa ~20 sn içinde kendi alır).

İşaretli satırın ilanı o an yayından kalkmışsa CV üretilmez: N sütununa `Kalkmış` yazılır, CV
numarası harcanmaz. Yine de üretmek istersen: `run_once.py --row <satır> --allow-staged`.

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 1. Google Service Account
Liste Drive'da bir **Excel (.xlsx)** dosyası olarak tutulur; uygulama dosyayı Drive API ile
indirir, openpyxl ile düzenler ve aynı dosyanın üzerine geri yükler.

1. Google Cloud Console'da bir proje açın ve **Google Drive API**'yi etkinleştirin.
2. Bir **Service Account** oluşturup JSON anahtarı indirin.
3. Anahtarı `credentials/service_account.json` olarak kaydedin.
4. Drive'daki `.xlsx` dosyanızı, service account e-postası ile (`...@...iam.gserviceaccount.com`)
   **Düzenleyen (Editor)** olarak paylaşın.
5. `.env` içindeki `SPREADSHEET_ID`, bu `.xlsx` dosyasının Drive linkindeki id'dir.

> Not: Dosya programatik olarak yeniden yazıldığı için açılır listeler (data validation) ve
> koşullu biçimlendirme korunur; yine de ilk çalıştırmadan önce dosyanın bir yedeğini almanız önerilir.

### 2. Ortam değişkenleri
```bash
cp .env.example .env
# .env içini doldurun: ANTHROPIC_API_KEY, SPREADSHEET_ID, SHEET_NAME, ...
```
`SHEET_NAME` sekme adıdır (Türkçe Google'da genelde `Sayfa1`).

### 3. LinkedIn oturumu (tek seferlik)
```bash
python scripts/linkedin_login.py
```
Açılan tarayıcıda LinkedIn'e giriş yapın, terminalde ENTER'a basın. Oturum
`credentials/linkedin_state.json` dosyasına kaydedilir. Çerezler süresi dolarsa
bu komutu tekrar çalıştırın.

### 4. Google Docs çıktısı için OAuth (tek seferlik)
Agent, her CV'yi `config/cv_template.docx` şablonundan üretip Drive'daki **"Resumes Based on
Jobs"** klasörüne `cv_<no>` adıyla **gerçek bir Google Doc** olarak da kaydeder. Service account
kişisel Drive'da yeni dosya oluşturamadığı için bu adım **OAuth** (kendi hesabınız) ile yapılır.

1. Google Cloud Console → **APIs & Services → OAuth consent screen** → External → kendinizi
   **Test user** ekleyin. (Token'ın 7 günde dolmaması için uygulamayı **Publish / Production**
   durumuna alın; kişisel kullanımda doğrulama gerekmez, "unverified" uyarısını kabul edin.)
2. **Credentials → Create credentials → OAuth client ID → Desktop app** → JSON'u indirin →
   `credentials/oauth_client.json` olarak kaydedin.
3. Drive'da **"Resumes Based on Jobs"** klasörünün var olduğundan emin olun (kendi hesabınız
   olduğu için paylaşım gerekmez).
4. Giriş yapın:
   ```bash
   python scripts/google_login.py
   ```
   Tarayıcıda izin verin → token `credentials/oauth_token.json` dosyasına kaydedilir.

> Bu adımı atlarsanız Markdown CV yine üretilir; sadece Google Doc oluşturma atlanır (loglanır).

## Çalıştırma

Sürekli izleme (polling):
```bash
python -m src.applyjobs.main
```

Tek seferlik tarama — normal kullanım (Finder'dan `scripts/cv_uret.command`'a çift tıklamak da
aynı şeyi yapar):
```bash
python scripts/run_once.py            # "Üretilecek" işaretli satırları işler
python scripts/run_once.py --dry-run  # sadece listeler, hiçbir şey yazmaz
python scripts/run_once.py --row 250 --allow-staged  # ilan kalkmış: panelin kaydettiği metinden üret
```

## Üretilen dosyalar

| Dosya | Konum |
|-------|-------|
| `cv_<no>.md` | `OUTPUT_DIR` (optimize CV, Markdown) |
| `cv_<no>.docx` | `OUTPUT_DIR` (Docs'a yüklenen yerel kopya) |
| `cv_<no>` (Google Doc) | Drive → "Resumes Based on Jobs" |
| `cv_<no>_analysis.md` | `ANALYSIS_DIR` (Türkçe ATS analizi + skor) |
| `job_description_<no>.md` | `JOB_DESCRIPTION_DIR` (çekilen ilan metni) |

## Yapı

```
config/      cv_base.md, projects.md, projects_list.md, ats_prompt.md, ats_review_prompt.md,
             cover_letter_prompt.md, cv_template.docx
credentials/ service_account.json, linkedin_state.json, oauth_client.json, oauth_token.json (gitignored)
extension/   Chrome MV3 eklentisi (panel): content.js, background.js, manifest.json
src/applyjobs/
  config.py        ayarlar, yollar, tetikleyici değerleri (CV_TRIGGER_BASVURU_VALUES)
  sheets.py        .xlsx indir/düzenle/yükle (service account) + dosya kilidi
  scraper.py       Playwright ile ilan açıklaması (yalnızca guest view)
  generator.py     Anthropic ile CV üretimi
  docx_builder.py  Markdown CV'yi .docx şablonuna doldurur
  drive_docs.py    .docx'i Google Doc'a dönüştürüp Drive'a yükler (OAuth)
  cover_letter.py  istek üzerine cover letter (dosyanın kendisi önbellektir)
  joblookup.py     CV No ↔ ilan no eşleştirme + panelin kaydettiği ilan metni
  summary_api.py   eklentinin FastAPI backend'i (özet, fit skoru, Ekle, Mektup)
  pipeline.py      satır işleme akışı
  reporting.py     log, hata kaydı, macOS bildirimi
  main.py          polling döngüsü
scripts/     cv_uret.command (çift tıkla → toplu üretim), run_once.py, regenerate.py,
             cover_letter.py, start.sh, start_api.sh, linkedin_login.py, google_login.py
state/       last_cv_no, pending_jd/, summary_cache.json, sheet.lock, agent.log,
             failures.log (gitignored)
```

## CV'ye ne eklenebilir? (dürüstlük kuralı)

CV'nin her satırı mülakatta savunulabilir olmalı, o yüzden `config/ats_prompt.md` ilandaki her
anahtar kelimeyi **üç tipe** ayırır:

| Tip | Ne demek | Kural |
|-----|----------|-------|
| **Hard-Tech** | Kurulabilen/import edilebilen **isimli teknoloji** (Redis, Kafka, Spring Boot, AWS) | 🔒 `cv_base.md` veya `projects.md`'de yoksa **CV'ye asla girmez** |
| **Hard-Practice** | Ürün adı içermeyen **pratik / aktivite / kalite özelliği** (debugging, best practices, documentation, testing, scalability, high-availability, distributed systems) | ✅ Soft skill gibi eklenir |
| **Soft** | Kişilerarası özellikler (communication, teamwork, attention to detail) | ✅ Hepsi eklenir |

Yani "sahte ekleme" **teknoloji** uydurmaktır — kullanılmamış bir teknolojiyi, yeni bir görev/alanı,
olmayan bir işvereni veya uydurma bir metriği yazmak. `debugging` yazmak sahtelik değildir: hiç kimse
yazdığı REST API'yi debug etmeden teslim etmez. Karışık terimler ikiye ayrılır: *containerization*
pratiktir, **Docker** teknolojidir. Tek sınır, pratik kelimesinin sırtında bir ölçek/olay iddiası
kaçırmamaktır (`high-availability principles` ✅, `1M+ istek işleyen high-availability sistemler` ❌).

Bold işaretleri bu kuralın denetim aracıdır: Markdown CV'de **yalnızca** `cv_base.md`'den farklı olan
kelimeler bold'dur, ve `.docx`/Doc/PDF'e bold **hiç geçmez** (kelimeler geçer, vurgu geçmez).

## Notlar
- Varsayılan model `claude-sonnet-4-6` (`.env`'de `CLAUDE_MODEL` ile değiştirilebilir).
- CV girdiniz değişirse `config/cv_base.md` ve `config/projects.md` dosyalarını güncelleyin. Prompt'a
  giden **detaylı** proje listesi `projects.md`'dir (`projects_list.md` kısa/özet sürümdür).
- ⚠️ `config/*.md` dosyaları **veri**dir, düzyazı değil: hiçbir formatter (Prettier vb.) dokunmamalı.
  Bir format-on-save `*` listelerini `-` yapınca CV'nin tüm madde imleri parse'tan düşmüştü.
  `.prettierignore` ve `.vscode/settings.json` bunu engelliyor.

## LinkedIn İlan Özet Extension'ı

LinkedIn iş arama sayfasında seçili ilanı okuyup sağ panelde kısa bir **Türkçe özet** gösteren Chrome
extension'ı (MV3). Özetleme, bu projeye entegre bir FastAPI servisi (`src/applyjobs/summary_api.py`)
üzerinden Claude ile yapılır. Model olarak **Haiku** kullanılır (`.env`'de `SUMMARY_MODEL`; CV üretiminin
`CLAUDE_MODEL`'inden ayrıdır). Çıkarılan alanlar: Rol Özeti, Çalışma Şekli, Vize/Sponsorluk, Birincil/
İkincil Dil, Araçlar, Framework'ler, Kütüphaneler, Min. Deneyim.

Panelde ayrıca **Ekle** butonu vardır: ilanı tabloya ekler (link/pozisyon/firma), B ve CV No'yu
boş bırakır. **CV üretmez** — üretim için B sütununu `Üretilecek` yapman gerekir (yukarıdaki
"Tetikleme kuralı"). Buton yalnızca API'ye ihtiyaç duyar.

**Tek komutla başlat (API + CV poller birlikte, Ctrl+C ikisini durdurur):**
```bash
./scripts/start.sh
```
Yalnız özet API'sini çalıştırmak için: `./.venv/bin/python scripts/run_summary_api.py`
(**Ekle** zaten CV üretmez; CV'yi `Üretilecek` işareti + `cv_uret.command` üretir.)

**Extension'ı yükle (bir kez):** `chrome://extensions` → Developer mode → **Load unpacked** →
`job-apply-agent/extension` klasörünü seç. Ardından `https://www.linkedin.com/jobs/` sayfasında bir ilana
tıkla; sağ üstte özet paneli belirir. (Not: extension LinkedIn'e hiçbir istek atmaz; sadece sayfadaki
metni okuyup localhost:8000'e gönderir.)
