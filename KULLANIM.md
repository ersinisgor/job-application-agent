# job-apply-agent — Kullanım Kılavuzu

Uygulama 7/24 kendi kendine çalışmaz. Drive'daki tabloyu **yalnızca sen terminalden
başlattığın sürece** izler. Aşağıdaki iki kullanım şeklinden birini seç.

> Her komuttan önce proje klasörüne girmen gerekir:
> ```bash
> cd /Users/mac/code/ersinisgor/job-apply-agent
> ```

---

## Seçenek A — Sürekli izleme ("başlat ve unut")

Terminal açık kaldığı sürece her 20 saniyede bir tabloyu kontrol eder; yeni ilan
girdikçe (elle ya da panelin **Ekle** butonuyla) otomatik işler (CV No + Match Rate + Google Doc).

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python -m src.applyjobs.main
```

- **Durdurmak için:** terminalde `Ctrl + C`
- ⚠️ Terminali kapatırsan, bilgisayarı kapatırsan veya **uyku moduna** geçerse izleme durur.
  Çalışması için pencere açık ve bilgisayar uyanık olmalı.

---

## Seçenek B — Tek seferlik (toplu)

Birkaç ilanı tabloya ekledikten sonra **bir kez** çalıştır; bekleyen tüm satırları
işleyip kapanır.

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python scripts/run_once.py
```

İşlemeden önce sadece hangi satırların işleneceğini görmek istersen (hiçbir şey yazmaz):

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python scripts/run_once.py --dry-run
```

Sadece tek bir satırı denemek istersen (örnek: 250. satır):

```bash
./.venv/bin/python scripts/run_once.py --row 250
```

---

## Seçenek C — Var olan bir CV'yi yeniden oluşturma (açıklamalı)

Üretilmiş bir CV'yi beğenmezsen (örn. yanlış projeleri eklemiş) **kaydedilmiş ilan
açıklamasından** yeniden ürettirirsin — LinkedIn'e tekrar gidilmez. Modele serbest bir
**açıklama** (`-i`) vererek CV'yi ona göre yeniden şekillendirebilirsin: hangi projeyi
çıkaracağını, hangisini öne çıkaracağını, neyi vurgulayacağını söylersin.

**Tek bir CV'yi (örnek: 309) açıklamayla yeniden oluştur:**
```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
CLAUDE_MODEL=claude-opus-4-8 CLAUDE_EFFORT=high ./.venv/bin/python scripts/regenerate.py \
  --from 309 --to 309 \
  -i "Remove the Library Management System project and feature a .NET project instead"
```

- **`--from` ve `--to` EŞİT olmalı** (tek CV için). Açıklama aralıktaki **her** CV'ye
  uygulanır — `--from 309 --to 312` yazarsan aynı açıklama dördüne de uygulanır.
- **`-i` açıklaması** İngilizce ya da Türkçe olabilir (CV yine İngilizce üretilir).
- **Dürüstlük kuralı geçerli:** eklenmesini istediğin proje/beceri **gerçek** olmalı
  (`config/projects.md` veya `config/cv_base.md`'de bulunmalı) — model uydurmaz.
- Açıklamasız da çalışır (sadece mevcut ayarlarla yeniden üretir): `-i`'yi yazmazsın.
- `--dry-run` eklersen hangi CV'lerin hedeflendiğini yazar, hiçbir şey üretmez.

> Model/effort'u güçlendirmek için baştaki `CLAUDE_MODEL=... CLAUDE_EFFORT=high` kısmını
> ekle; yazmazsan `.env`'deki varsayılan kullanılır.

---

## ⚠️ ÖNEMLİ: Yeni ilan girerken veri kaybını önleme

Uygulama, tabloyu güncellerken **tüm `.xlsx` dosyasını indirip geri yükler.** Sen aynı anda
tabloyu tarayıcıda düzenliyorsan, senin yazdıkların Drive'a gecikmeli kaydedildiği için
çakışma olur ve uygulamanın yüklediği sürüm senin son girdiğin hücreleri (B/C/F/G/H gibi)
silebilir. (Uygulama bu sütunlara asla yazmaz; sorun eşzamanlı düzenlemeden kaynaklanır.)

**Kural — yeni bir ilan satırı eklerken:**
1. Satırın **tüm** bilgilerini gir (Başvuru, Easy Apply, Yer, Uzaktan, Çalışma Şekli, İlan Linki...).
2. **~15-20 saniye bekle** (Google'ın kaydetmesi için) veya tablo sekmesini kapat.
3. Sonra uygulamanın işlemesine bırak.
4. Uygulama o satırı işlerken (~1.5 dk) **o satırı tarayıcıda düzenleme.**

> Not: Uygulama artık tabloya **yalnızca CV üretildikten sonra, tek seferde** yazıyor (CV No + Match Rate
> birlikte). Bu, senin girişlerine ~1.5 dk senkronizasyon süresi tanır ve çakışma riskini azaltır — ama
> yukarıdaki kurala uymak yine de en güvenlisidir.
>
> En kesin yöntem: ilanları gir, tabloyu kapat, sonra **Seçenek B** (tek seferlik) ile çalıştır.

⚠️ **Yeni:** Panelin **Ekle** butonu geldiğinden beri uygulama **sen LinkedIn'de gezerken de**
tabloya yazıyor (yeni satır ekliyor). Yani "sadece işleme sırasında yazar" varsayımı artık geçerli
değil — **LinkedIn'de ilan bakarken tablo sekmesini kapalı tut.** Yeni satırlar her zaman en alta
eklenir, o yüzden üstteki düzenlediğin satırlara dokunmaz; ama dosyanın tamamı yine geri yüklenir.

## Hangi satırlar işlenir?

İlan linki (K) dolu **ve** CV No (N) boş olan satırlar.
B sütunu (Başvuru) şu değerlerdeyse **atlanır:** `Geçmiş`, `Vazgeçildi`, `Başvurulmuş`, `✓`.
Yani `+`, `++` veya boş olanlar işlenir.

## Üretilen dosyalar

| Çıktı | Konum |
|-------|-------|
| `cv_<no>.md` | Masaüstü/İş Arama/Job Applications/2026/CVs |
| `cv_<no>.docx` | aynı CVs klasörü (yerel kopya) |
| `cv_<no>` (Google Doc) | Drive → Resumes based on Jobs |
| `cv_<no>_analysis.md` | .../2026/CV_Analysis |
| `job_description_<no>.md` | .../2026/Job Description |
| CV No → N sütunu, Match Rate → P sütunu | Drive'daki tablo |

---

## İlan ekleme — panel "Ekle" butonu

Başvurmak istediğin LinkedIn ilanındayken paneldeki **Ekle** butonuna bas. Tabloya yeni bir
satır eklenir: **İlan Linki (K), Pozisyon (L), Firma (J)**. CV No (N) boş bırakılır — poller
onu ~20 saniye içinde görüp ilan sayfasına gidip **Yer (F)** ve **Çalışma Şekli (H)** sütunlarını
da doldurur (sadece boş hücreleri) ve CV'yi üretir.

- **G (Uzaktan)** otomatik doldurulmaz → elle girersin (LinkedIn bu bilgiyi otomasyona vermiyor).
- **C (Easy Apply)** LinkedIn ilanlarında boş kalır (elle), LinkedIn dışı linklerde "Yok".
- Buton **API'ye ihtiyaç duyar, CV ise poller'a** — bu yüzden normal kullanım `./scripts/start.sh`
  (ikisini birlikte başlatır). Sadece `start_api.sh` çalışıyorsa satır eklenir ama CV üretilmez.

**Buton etiketleri:**

| Etiket | Anlamı |
|--------|--------|
| `Ekle` | ilan henüz tabloda değil |
| `Ekleniyor…` | istek gidiyor |
| `Eklendi ✓` | satır eklendi (ilan metni de yedek olarak kaydedildi) |
| `Eklendi (metin yok)` | satır eklendi ama sayfadan açıklama okunamadı — poller yine de scrape edecek |
| `Zaten var` / `Zaten var · CV 312` | bu ilan tabloda zaten kayıtlı, ikinci satır açılmadı |
| `Hata` | üzerine gel, hata mesajı tooltip'te |

**İlan açıklaması yedeği:** Ekle'ye bastığında panelin ekranda okuduğu ilan metni
`state/pending_jd/<ilan_no>.md` dosyasına da kaydedilir. Poller normalde ilan sayfasını kendisi
okur (birincil kaynak); **sadece bu okuma başarısız olursa** (ilan kaldırılmış, LinkedIn duvarı)
kaydedilen metne düşer ve CV yine üretilir. Böyle bir durumda macOS bildirimi gelir. CV yazıldıktan
sonra dosya silinir.

### Huntr (artık kapalı)

`.env`'de `HUNTR_BOARD_URL` boş → Huntr hiç çalışmıyor. Kod duruyor; geri açmak için board
adresini o satıra yazman yeterli (`./.venv/bin/python scripts/huntr_login.py` ile bir kez giriş
yapman gerekir, ilk çalıştırmada mevcut ilanlar "görüldü" işaretlenir).

## Kimlik bilgileri (tekrar gerekir mi?)

- **Anthropic / Google OAuth / Service Account:** kalıcı, tekrar giriş gerekmez.
- **LinkedIn çerezleri:** zamanla dolabilir. İlan açıklamaları çekilemezse (loglarda
  LinkedIn hatası) bir kez daha çalıştır:
  ```bash
  ./.venv/bin/python scripts/linkedin_login.py
  ```

---

## Sık karşılaşılan durumlar

- **"command not found: python" benzeri hata:** `python` yerine her zaman `./.venv/bin/python`
  yaz (projeye özel Python budur).
- **Yanlış klasördeyim:** her komuttan önce `cd /Users/mac/code/ersinisgor/job-apply-agent`.
- **Bir ilan atlandı:** ilan yayından kalkmış olabilir; o satır işlenmez, diğerleri devam eder.
  İlgili satırın CV No (N) hücresini silip tekrar çalıştırırsan yeniden denenir.

---

## LinkedIn İlan Özet Extension'ı (Chrome)

LinkedIn'de bir ilana tıkladığında sağ üstte kısa bir **Türkçe özet** gösterir. Özetleme, bu projeye
entegre FastAPI servisiyle (Haiku modeli) yapılır.

**1. Tek komutla başlat** (özet API + CV poller birlikte; Ctrl+C ikisini birden durdurur):
```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./scripts/start.sh
```
> Sadece özet API'sini istersen: `./.venv/bin/python scripts/run_summary_api.py`

**2. Extension'ı Chrome'a yükle (yalnızca ilk sefer):**
- `chrome://extensions` → sağ üstten **Developer mode** aç.
- **Load unpacked** → `job-apply-agent/extension` klasörünü seç.

**3. Kullan:** `https://www.linkedin.com/jobs/` sayfasında bir ilana tıkla → sağ panelde Türkçe özet.
Başka ilana geçince güncellenir; daha önce baktığın ilana dönünce anında (önbellekten) gelir.

**Sık durumlar:**
- Panelde **"Backend unreachable…"**: `./scripts/start.sh` (veya `run_summary_api.py`) çalışmıyor.
- Panelde **"ANTHROPIC_API_KEY is not set"**: `.env`'de anahtar eksik.
- Özet modeli `.env`'deki `SUMMARY_MODEL` (varsayılan `claude-haiku-4-5`) ile değişir.
