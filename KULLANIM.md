# job-apply-agent — Kullanım Kılavuzu

Uygulama 7/24 kendi kendine çalışmaz. Drive'daki tabloyu **yalnızca sen terminalden
başlattığın sürece** izler. Aşağıdaki iki kullanım şeklinden birini seç.

> ## 🤖 CV'leri artık Claude Code agent'ları üretiyor
>
> Komutlar ve butonlar eskisi gibi. Fark perde arkasında: CV ve mektup artık doğrudan API ile
> değil, **Claude Code agent'larıyla** (senin Claude aboneliğinle) üretiliyor. Bunun için bir kez
> terminalde `claude` yazıp Claude Code'a giriş yapmış olman yeterli. Kontrol: `claude mcp list`
> çıktısında `cv-tools: ✔ Connected` görünmeli.
>
> - Bir CV medium effort'ta **~2-6 dakika** sürer. Para faturalanmaz, abonelik kotandan düşer.
> - Üretilen her şey artık **proje klasöründe**, `outputs/` altında (GitHub'a gitmez). Eski
>   masaüstü klasörün yedek olarak duruyor.
> - Aynı akışları Claude Code'un içinden de çalıştırabilirsin (bkz.
>   [Claude Code içinden kullanım](#claude-code-içinden-kullanım)).

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

Terminal açık kaldığı sürece her 20 saniyede bir tabloyu kontrol eder. Bu kontrol model
çağırmaz. **B sütunu `Üretilecek` yapılmış** bir satır görünce CV agent'ını başlatır
(CV No + Match Rate + Google Doc). Bir satır hata verirse aynı satır 15 dakika boyunca yeniden
denenmez, kota boşa harcanmasın diye.

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
CV_MODEL=claude-opus-5-5 CV_EFFORT=high ./.venv/bin/python scripts/regenerate.py \
  --from 309 --to 309 \
  -i "Remove the Library Management System project and feature a .NET project instead"
```

- **`--from` ve `--to` EŞİT olmalı** (tek CV için). Açıklama aralıktaki **her** CV'ye
  uygulanır — `--from 309 --to 312` yazarsan aynı açıklama dördüne de uygulanır.
- **`-i` açıklaması** İngilizce ya da Türkçe olabilir (CV yine İngilizce üretilir).
- **Dürüstlük kuralı geçerli:** eklenmesini istediğin **proje veya teknoloji** gerçek olmalı
  (`profile/projects.md` veya `profile/cv_base.md`'de bulunmalı) — model uydurmaz. Buna karşılık
  *debugging, best practices, documentation, testing, scalability, high-availability* gibi
  **ürün adı olmayan** ifadeler artık serbestçe eklenebiliyor (aşağıya bak).
- Açıklamasız da çalışır (sadece mevcut ayarlarla yeniden üretir): `-i`'yi yazmazsın.
- `--dry-run` eklersen hangi CV'lerin hedeflendiğini yazar, hiçbir şey üretmez.

> Model/effort'u güçlendirmek için baştaki `CV_MODEL=... CV_EFFORT=high` kısmını
> ekle; yazmazsan `.env`'deki varsayılan (`claude-sonnet-5`, `medium`) kullanılır.
> (Eski `CLAUDE_MODEL` / `CLAUDE_EFFORT` adları artık kullanılmıyor: `CLAUDE_EFFORT`, Claude
> Code'un kendi değişkeniyle çakışıp `.env`'deki değeri sessizce eziyordu.)

---

## Claude Code içinden kullanım

Proje klasöründe `claude` yazıp Claude Code'u açtıysan aynı işleri komutla da yaptırabilirsin:

| Komut | Ne yapar |
|-------|----------|
| `/cv-uret` | `Üretilecek` işaretli bütün satırlar için CV üretir (`--row 250`, `--limit 1`, `--allow-staged` de olur) |
| `/cv-yenile 309 309 Remove project X, feature a .NET project` | CV 309'u kaydedilmiş ilandan, talimatla yeniden üretir |
| `/mektup 305 tr` | CV 305 için Türkçe mektup (`--force` ile yeniden üretir) |
| `/loop 10m /cv-uret` | poller yerine: oturum açık kaldıkça her 10 dakikada bir kontrol eder |

Bu komutlar terminaldeki script'lerin yaptığının aynısını yapar; script'ler de perde arkasında
bunları `claude -p` ile çalıştırır.

---

## Cover letter (Mektup) — istek üzerine, tek tek

Her başvuru cover letter istemediği için mektuplar CV ile birlikte üretilmez; **sen istediğinde,
tek bir iş için** üretilir. Mektup; o işe özel üretilmiş **CV'den + kaydedilmiş ilan
açıklamasından + `profile/projects.md`'den** yazılır — yani ilan yayından kalkmış olsa bile çalışır,
LinkedIn'e tekrar gidilmez.

**Yol 1 — panelden (en pratik):** LinkedIn'de o ilandayken paneldeki **Mektup** butonuna bas.

| Panelde ne var | Ne yapar |
|----------------|----------|
| `EN` / `TR` | mektubun dili — ikisi **ayrı** mektuptur, TR'ye basmak EN'i geri vermez |
| `Kopyala` | mektubu panoya kopyalar (ayrı bir tık olması gerekiyor, tarayıcı kuralı) |
| `Yeniden üret` | kayıtlı mektubu **silip** yeniden yazdırır |
| `Mektup` (tekrar) | mektup görünümünü kapatır, özete döner |

Başlıkta `CV 312 · kayıtlı mektup` ya da `· yeni üretildi` yazar. Buton **API'ye** ihtiyaç duyar
(`./scripts/start_api.sh` veya `start.sh`).

**Yol 2 — terminalden:**

```bash
cd /Users/mac/code/ersinisgor/job-apply-agent
./.venv/bin/python scripts/cover_letter.py --cv-no 305             # İngilizce, panoya kopyalar
./.venv/bin/python scripts/cover_letter.py --cv-no 305 --lang tr   # Türkçe
./.venv/bin/python scripts/cover_letter.py --cv-no 305 --force     # yeniden üret, üzerine yaz
./.venv/bin/python scripts/cover_letter.py --cv-no 305 --no-copy   # panoya dokunma
```

**Bilinmesi gerekenler:**

- **Dosyanın kendisi önbellektir.** Mektup `outputs/cover_letters/`
  altına `cover_letter_<no>_<dil>.md` olarak yazılır. Aynı iş+dil için tekrar istersen model
  çağrılmaz, kayıtlı dosya verilir. Yeniden yazdırmanın tek yolu `--force` / **Yeniden üret**.
- **Kimlik (iş, dil) çiftidir:** `cover_letter_305_en.md` ve `cover_letter_305_tr.md` iki ayrı
  mektuptur.
- **Yalnızca CV No ≥ 200 için üretilebilir.** Daha eski işlerde ne `cv_<no>.md` ne de
  `job_description_<no>.md` saklanmış, dayanacak bir şey yok.
- **Sheet'te J (Firma) ve L (Pozisyon) dolu olmalı** — yanlış şirket adı taşıyan bir mektup işe
  yaramaz, o yüzden tahmin etmek yerine hata verir.
- **İmza hazır gelir** (`Saygılarımla, / Best regards, + Ersin Isgor`), dosyanın başındaki
  `<!-- cv_no: … -->` künye satırı panoya/panele **geçmez**.
- **Dürüstlük kuralı burada da geçerli:** `projects.md` yalnızca senin kendi projelerine *detay*
  ekleyebilir (hangi teknoloji, nasıl kurgulanmış); yeni bir işveren/görev/metrik ekleyemez ve
  kişisel bir projeyi profesyonel deneyim gibi gösteremez.
- **Uzunluk 150-200 kelime.** Mektubu cover-letter-writer agent'ı yazar; yeni bir mektup
  ~30-60 saniye sürer (panelde "Mektup hazırlanıyor…" yazar), kayıtlı mektup anında gelir.

**Panelde çıkabilecek hatalar:**

| Mesaj | Anlamı |
|-------|--------|
| `Bu ilan (…) tabloda yok — önce "Ekle" ile ekle.` | satır hiç eklenmemiş |
| `Bu ilan tabloda (satır …) ama CV'si henüz üretilmedi.` | B'yi `Üretilecek` yapıp CV'yi üretmen gerekiyor |
| `… 200'den küçük CV'ler için mektup üretilemiyor.` | eski iş, kaynak dosyalar yok |

---

## CV'ye ne eklenebilir, ne eklenemez?

CV'nin her satırını mülakatta savunabilmen gerekiyor. Kurallar
(`.claude/skills/ats-cv-kurallari/`) ilandaki her anahtar kelimeyi **üç tipe** ayırıyor:

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
4. Uygulama o satırı işlerken (~2-6 dk) **o satırı tarayıcıda düzenleme.**

> Not: Uygulama artık tabloya **yalnızca CV üretildikten sonra, tek seferde** yazıyor (CV No + Match Rate
> birlikte). Bu, senin girişlerine birkaç dakikalık senkronizasyon süresi tanır ve çakışma riskini azaltır — ama
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
| `cv_<no>.md` | `outputs/cv/markdown/` |
| `cv_<no>.pdf` | `outputs/cv/pdf/` |
| `cv_<no>` (Google Doc) | Drive → Resumes based on Jobs |
| `cv_<no>_analysis.md` | `outputs/cv/analysis/` (Türkçe ATS analizi + skor) |
| `job_description_<no>.md` | `outputs/job_descriptions/` |
| `cover_letter_<no>_<dil>.md` | `outputs/cover_letters/` (yalnızca istediğinde — bkz. [Cover letter](#cover-letter-mektup--istek-üzerine-tek-tek)) |
| CV No → N sütunu, Match Rate → P sütunu, Yazılım Dili → Q sütunu | Drive'daki tablo |

`outputs/` klasörü `.gitignore`'da: kişisel veridir, GitHub'a gitmez. CV numaraları eskisi gibi
devam eder (sheet'teki en büyük N ile `state/last_cv_no`'dan büyük olanı + 1).

---

## İlan ekleme — panel "Ekle" butonu

İlgini çeken LinkedIn ilanındayken paneldeki **Ekle** butonuna bas. Tabloya yeni bir
satır eklenir: **İlan Linki (K), Pozisyon (L), Firma (J)**. B ve CV No (N) boş bırakılır.

⚠️ **Ekle CV üretmez.** Satır sen `B = Üretilecek` yapana kadar bekler. Üretim sırasında
**Yer (F)** ve **Çalışma Şekli (H)** sütunları da ilan sayfasından doldurulur (sadece boş hücreler).

- **G (Uzaktan)** otomatik doldurulmaz → elle girersin (LinkedIn bu bilgiyi otomasyona vermiyor).
- **C (Easy Apply)** LinkedIn ilanlarında boş kalır (elle), LinkedIn dışı linklerde "Yok".
- Buton **API'ye ihtiyaç duyar** (`./scripts/start_api.sh` veya `start.sh`). CV üretimi ise ayrı:
  ya poller açık olacak, ya da `scripts/cv_uret.command`'a çift tıklayacaksın (CV'yi agent üretir).

**Buton etiketleri:**

| Etiket | Anlamı |
|--------|--------|
| `Ekle` | ilan henüz tabloda değil |
| `Ekleniyor…` | istek gidiyor |
| `Eklendi ✓` | satır eklendi (ilan metni de yedek olarak kaydedildi) |
| `Eklendi (metin yok)` | satır eklendi ama sayfadan açıklama okunamadı — CV agent'ı ilanı yine kendisi okuyacak |
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

- **Anthropic API anahtarı / Google OAuth / Service Account:** kalıcı, tekrar giriş gerekmez.
  (API anahtarı artık yalnızca panel özeti için kullanılıyor.)
- **Claude Code girişi:** CV ve mektup agent'ları için gerekli. Agent çalışmaları "not logged in"
  benzeri bir hatayla bitiyorsa terminalde `claude` yazıp yeniden giriş yap.
- **LinkedIn:** giriş gerekmez ve **yapılmamalı**. İlanlar herkese açık görünümden okunur;
  `linkedin_login.py`'nin ürettiği oturumu hiçbir otomasyona bağlama (hesabın işaretlenip bütün
  oturumların kapanmasına yol açmıştı).

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
- **"Başka bir CV üretimi zaten çalışıyor":** poller ve `cv_uret.command` aynı anda çalışmasın diye
  kilit var. Diğeri bitince tekrar dene (poller zaten bir sonraki turda alır).
- **Agent'ın ne yaptığını görmek:** `state/agent.log` (agent raporu, süre, maliyet) ve
  `state/mcp.log` (araç çağrıları); hatalar `state/failures.log`'da.
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

**Paneldeki butonlar:** `Ekle` (ilanı tabloya yaz — CV üretmez, yukarı bak) ve `Mektup` (o iş için
cover letter — [Cover letter bölümü](#cover-letter-mektup--istek-üzerine-tek-tek)).

**Sık durumlar:**
- Panelde **"Backend unreachable…"**: `./scripts/start.sh` (veya `run_summary_api.py`) çalışmıyor.
- Panelde **"ANTHROPIC_API_KEY is not set"**: `.env`'de anahtar eksik.
- Özet modeli `.env`'deki `SUMMARY_MODEL` (varsayılan `claude-haiku-4-5`) ile değişir.
