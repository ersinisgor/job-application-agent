# job-apply-agent — Kullanım Kılavuzu

Uygulama 7/24 kendi kendine çalışmaz. Drive'daki tabloyu **yalnızca sen terminalden
başlattığın sürece** izler. Aşağıdaki iki kullanım şeklinden birini seç.

> Her komuttan önce proje klasörüne girmen gerekir:
> ```bash
> cd /Users/mac/code/ersinisgor/job-apply-agent
> ```

---

> ## ⚡ Önce şunu bil: CV artık ilanı eklerken değil, **sen isteyince** üretilir
>
> Panelin **Ekle** butonu satırı tabloya yazar, **CV üretmez**. Başvurmaya karar verdiğin gün
> o satırın **B (Başvuru)** sütununu dropdown'dan **`Üretilecek`** yap — CV ancak o zaman üretilir.
>
> Sebebi: eklediğin ilana çoğu zaman aynı gün başvuramıyorsun, sıra geldiğinde ilan kalkmış
> oluyordu ve hiç başvurmayacağın ilanlara CV üretilmiş oluyordu.
>
> **Toplu üretim:** işaretlemeyi bitirdikten sonra Finder'dan `scripts/cv_uret.command`
> dosyasına **çift tıkla** — işaretli tüm satırlar için CV üretir, özet basar, kapanır.
> (Poller açıksa zaten ~20 saniye içinde kendisi alır; ikisi aynı işi yapar.)
>
> **İşaretlediğin ilan kalkmışsa** CV üretilmez: o satırın **N** sütununa `Kalkmış` yazılır ve
> hiçbir CV numarası harcanmaz.

---

## Seçenek A — Sürekli izleme ("başlat ve unut")

Terminal açık kaldığı sürece her 20 saniyede bir tabloyu kontrol eder; **B sütunu `Üretilecek`
yapılmış** satırları otomatik işler (CV No + Match Rate + Google Doc).

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python -m src.applyjobs.main
```

- **Durdurmak için:** terminalde `Ctrl + C`
- ⚠️ Terminali kapatırsan, bilgisayarı kapatırsan veya **uyku moduna** geçerse izleme durur.
  Çalışması için pencere açık ve bilgisayar uyanık olmalı.

---

## Seçenek B — Tek seferlik (toplu) ← normal kullanım

Tabloda başvuracağın satırların **B sütununu `Üretilecek`** yap, kaydet, sonra **bir kez**
çalıştır; işaretli tüm satırları işleyip kapanır.

**En kolayı — çift tıkla:** Finder'da `job-apply-agent/scripts/cv_uret.command` dosyasına çift
tıkla. Terminal açılır, üretimi yapar, `Kapatmak için bir tuşa bas...` der.

Terminalden aynı şey:

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python scripts/run_once.py
```

Sonunda tek satırlık özet gelir: `Scan complete: 3 CV(s) generated, 1 expired, 0 failed.`

İşlemeden önce sadece hangi satırların işleneceğini görmek istersen (hiçbir şey yazmaz):

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python scripts/run_once.py --dry-run
```

Sadece tek bir satırı denemek istersen (örnek: 250. satır — o satır da `Üretilecek` olmalı):

```bash
./.venv/bin/python scripts/run_once.py --row 250
```

İlan gerçekten kalkmış ama **yine de** CV istiyorsan (Ekle'de kaydedilen ilan metninden üretir;
önce o satırın N hücresindeki `Kalkmış` yazısını sil):

```bash
./.venv/bin/python scripts/run_once.py --row 250 --allow-staged
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
- **Dürüstlük kuralı geçerli:** eklenmesini istediğin **proje veya teknoloji** gerçek olmalı
  (`config/projects.md` veya `config/cv_base.md`'de bulunmalı) — model uydurmaz. Buna karşılık
  *debugging, best practices, documentation, testing, scalability, high-availability* gibi
  **ürün adı olmayan** ifadeler artık serbestçe eklenebiliyor (aşağıya bak).
- Açıklamasız da çalışır (sadece mevcut ayarlarla yeniden üretir): `-i`'yi yazmazsın.
- `--dry-run` eklersen hangi CV'lerin hedeflendiğini yazar, hiçbir şey üretmez.

> Model/effort'u güçlendirmek için baştaki `CLAUDE_MODEL=... CLAUDE_EFFORT=high` kısmını
> ekle; yazmazsan `.env`'deki varsayılan kullanılır.

---

## CV'ye ne eklenebilir, ne eklenemez?

CV'nin her satırını mülakatta savunabilmen gerekiyor. Prompt ilandaki her anahtar kelimeyi
**üç tipe** ayırıyor:

| Tip | Örnek | Ne olur |
|-----|-------|---------|
| **Teknoloji** (Hard-Tech) | Redis, Kafka, Spring Boot, AWS, Oracle | 🔒 `cv_base.md`/`projects.md`'de yoksa **hiç yazılmaz** — "(fundamentals)" gibi kaçamak da yok |
| **Pratik** (Hard-Practice) | debugging, best practices, documentation, code review, testing, scalability, maintainability, high-availability, distributed systems, async communication | ✅ **Eklenir** — bunlar ürün değil, zaten yaptığın işin doğal parçası |
| **Soft skill** | communication, teamwork, attention to detail | ✅ Hepsi eklenir |

**Neden değişti:** eskiden prompt yalnızca Hard/Soft ayrımı biliyordu, bu yüzden `Debugging` veya
`Best Practices` gibi ifadeleri "sahte hard skill" sayıp CV'ye yazmıyordu (bkz. `cv_324_analysis.md`).
Bunlar teknoloji değil; yazmamak ATS puanı kaybettiriyordu, dürüstlük olarak hiçbir şey kazandırmıyordu.

**Sahte ekleme** hâlâ şudur: kullanmadığın bir teknoloji, yapmadığın bir görev/alan, olmayan bir
işveren/müşteri, uydurma bir metrik. Karışık terimler ikiye ayrılır: *containerization* pratiktir,
**Docker** teknolojidir; *version control* pratiktir, **Git** teknolojidir. Pratik kelimesinin
sırtında ölçek iddiası da kaçamaz: `high-availability principles` ✅ / `1M+ istek işleyen
high-availability sistemler` ❌.

> Markdown CV'de **bold**, `cv_base.md`'ye göre değişen kelimeleri gösterir — yani neyin eklendiğini
> tek bakışta denetleyebilirsin. `.docx`/Google Doc/PDF'e bu vurgu hiç geçmez, sadece kelimeler geçer.

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

Üç şartın **üçü birden**: İlan linki (K) dolu + CV No (N) boş + **B sütunu (Başvuru) = `Üretilecek`**.

| B sütunu | Ne olur |
|----------|---------|
| `Üretilecek` | ✅ CV üretilir (tek tetikleyici bu) |
| boş | ⏸ hiçbir şey — satır bekler, sen işaretleyene kadar |
| `Olabilir` / `Başvurulmuş` / `✓` / `Geçmiş` / `Vazgeçildi` | ⏸ atlanır |

N sütunu hâlâ "yapıldı mı?" sorusunun cevabı: doluysa satır bir daha işlenmez. İçindeki
`Kalkmış` yazısı "ilan yayından kalkmıştı, CV üretilmedi" demektir — silip B'yi tekrar
`Üretilecek` yaparsan yeniden denenir.

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

İlgini çeken LinkedIn ilanındayken paneldeki **Ekle** butonuna bas. Tabloya yeni bir
satır eklenir: **İlan Linki (K), Pozisyon (L), Firma (J)**. B ve CV No (N) boş bırakılır.

⚠️ **Ekle CV üretmez.** Satır sen `B = Üretilecek` yapana kadar bekler. Üretim sırasında
**Yer (F)** ve **Çalışma Şekli (H)** sütunları da ilan sayfasından doldurulur (sadece boş hücreler).

- **G (Uzaktan)** otomatik doldurulmaz → elle girersin (LinkedIn bu bilgiyi otomasyona vermiyor).
- **C (Easy Apply)** LinkedIn ilanlarında boş kalır (elle), LinkedIn dışı linklerde "Yok".
- Buton **API'ye ihtiyaç duyar** (`./scripts/start_api.sh` veya `start.sh`). CV üretimi ise ayrı:
  ya poller açık olacak, ya da `scripts/cv_uret.command`'a çift tıklayacaksın.

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
`state/pending_jd/<ilan_no>.md` dosyasına da kaydedilir. Üretim sırasında ilan sayfası **normalde
yeniden okunur** (birincil kaynak); okuma başarısız olursa artık bu yedeğe **otomatik düşülmez** —
satır `Kalkmış` işaretlenir ve CV üretilmez. Yedeği kullanmak isteyip istemediğine sen karar
verirsin: `run_once.py --row <satır> --allow-staged`. CV yazıldıktan sonra dosya silinir
(kullanılmayanlar 14 gün sonra temizlenir).

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
- **Bir ilan atlandı / N'de `Kalkmış` yazıyor:** ilan yayından kalkmış (ya da LinkedIn okumayı
  engellemiş); o satır için CV üretilmedi, CV numarası da harcanmadı, diğerleri devam etti.
  Tekrar denemek için N hücresini sil ve B'yi yine `Üretilecek` yap. İlan gerçekten kalktıysa ve
  yine de CV istiyorsan: `./.venv/bin/python scripts/run_once.py --row <satır> --allow-staged`.
- **Hiçbir satır işlenmiyor ("No candidate rows"):** muhtemelen B sütununu `Üretilecek`
  yapmayı unuttun. Kontrol: `./.venv/bin/python scripts/run_once.py --dry-run`.
- **CV'ye yeni bir proje takıldıysa PDF'i de bir kontrol et:** listeden proje değiştirildiğinde
  o bloğun tamamı yeni sayılır ve model başlığı/`Tech:` satırını da bold yazar. Bu iki satırın
  `.docx`/PDF'e taşınması 2026-08-10'da düzeltildi (öncesinde takılan proje bir önceki projenin
  teknoloji listesiyle görünüyordu; etkilenen 16 CV'nin PDF'i yeniden üretildi). Gördüğün Markdown
  ile PDF hâlâ ayrışıyorsa bu sınıf bir hata geri gelmiş demektir.

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
