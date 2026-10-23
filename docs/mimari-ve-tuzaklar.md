# Mimari ve tuzaklar (geliştirici notları)

Bu dosya, koda dokunmadan önce bilinmesi gerekenleri toplar. Kısa yönerge `CLAUDE.md`'de;
burası "neden böyle?" sorularının cevabı. Değişiklik yaparken ilgili bölümü güncel tut.

## 1. Agent katmanı

**İlke: değişmezler araçlarda, muhakeme agent'larda.** LLM akışı yönetir ve CV/mektup yazar;
CV numarası ayırma, `Kalkmış` işaretleme, tekrar kontrolü, sheet kilidi ve çıktı ayrıştırma
mevcut Python kodunda (cv-tools MCP sunucusunun içinde) kalır. Agent bir numarayı yanlış yazsa ya
da bir adımı atlasa bile sheet bozulmaz: numara ve satır alanları `mcp_server.py`'nin belleğinde
tutulur, agent'tan geri okunmaz.

| Parça | Dosya | Not |
|---|---|---|
| Orkestratör | `.claude/commands/cv-uret.md`, `cv-yenile.md`, `mektup.md` | Ana oturum; sadece `mcp__cv-tools__*` + subagent kullanır |
| Drafter | `.claude/agents/cv-writer.md` | `tools: Read, Write`; çıktıyı tek analiz dosyasına yazar |
| Reviewer | `.claude/agents/cv-reviewer.md` | Yalnızca `CV_REVIEW=on` |
| Mektup | `.claude/agents/cover-letter-writer.md` | `save_cover_letter` aracını kendisi çağırır |
| Kurallar | `.claude/skills/ats-cv-kurallari/`, `mektup-kurallari/` | `skills:` ile subagent'a önceden yüklenir; `user-invocable: false` |
| Araçlar | `src/applyjobs/mcp_server.py` + `.mcp.json` | FastMCP değil: `mcp` 2.x'te sınıf adı `MCPServer` |
| Başlatıcı | `src/applyjobs/agent_runner.py` | `claude -p` alt süreci |
| Hook'lar | `.claude/hooks/guard_secrets.py`, `check_cv_output.py` | `.claude/settings.json`'da kayıtlı |
| Döngü | `src/applyjobs/main.py` | Aday yoksa hiç agent başlatmaz |

### agent_runner: neden bu bayraklar

- **`ANTHROPIC_API_KEY` child ortamdan silinir.** `.env` bu anahtarı (panel özeti için) yüklüyor;
  `claude -p` ortamda anahtar görürse girişli aboneliği değil API'yi faturalar. Doğrulama: başsız
  oturumun `init` mesajında `apiKeySource: "none"` görünmeli.
- **`CLAUDE_EFFORT` silinir, `CV_EFFORT` kullanılır.** Claude Code kendi effort'unu `CLAUDE_EFFORT`
  adıyla her Bash komutuna ihraç ediyor ve `load_dotenv` var olan değişkeni ezmiyor; eski adla
  `.env`'deki değer Claude Code içinden çalışınca sessizce yok sayılıyordu (2026-07-16'da bulundu).
- **`CLAUDECODE` silinir:** bir Claude Code oturumunun içinden başlatılan iç içe `claude` bunu görünce
  çalışmayı reddediyor.
- **`--permission-mode dontAsk`:** izin listesinde (`.claude/settings.json`) olmayan her şey sormadan
  reddedilir; başsız oturum asla bir onay ekranında takılmaz. `-p` modunda doğrulamadan geçemeyen
  bir settings dosyası **sessizce yok sayılır** — izin kuralı eklerken standart sözdizimini kullan.
- **`--disallowedTools Bash,WebFetch,WebSearch`:** agent'lar dış dünyaya yalnızca cv-tools üzerinden
  dokunur. LinkedIn'i sadece o sunucudaki misafir görünümlü scraper okur.
- **`--strict-mcp-config --mcp-config .mcp.json`:** kullanıcının claude.ai bağlayıcıları (Drive,
  Docs…) başsız CV oturumuna yüklenmez.
- **`state/agent_cv.lock`:** `/cv-uret` ve `/cv-yenile` aynı anda iki kez çalışmaz (poller ile
  `cv_uret.command` aynı satıra iki CV üretip numarayı iki kez harcamasın). Mektup kilit almaz.
- `claude` yolu: `CLAUDE_BIN` → PATH → `~/.local/bin/claude` (Finder'dan açılan `.command`'da PATH dar).

### Dosya tabanlı devir teslim

cv-writer çıktısını eski API çağrısının "full response" biçiminde tek dosyaya yazar:
`outputs/cv/analysis/cv_<no>_analysis.md` = Türkçe analiz + `<CV_START>…<CV_END>` +
`<MATCH_RATE>` + `<LANGUAGES>`. `finalize_cv` bu dosyayı `cv_output.parse_agent_output` ile okur
(ayrıştırıcılar eski `generator.py` ile birebir aynı; 175 eski analizde 0 fark). Böylece orkestratör
uzun metni bağlamında taşımaz ve biçim eski CV'lerle uyumlu kalır.

- `prepare_job` ayırdığı numaranın bayat analiz/review dosyalarını siler (o numara hiçbir satıra ait
  değil). `_read_agent_output`, dosya bu çalışma başladıktan **sonra** yazılmamışsa hata verir;
  yoksa önceki bir denemenin dosyası sessizce kullanılırdı.
- Review dosyası yalnızca `CV_REVIEW` açıksa ve analizden yeni ise kullanılır. Eski generate+review
  mantığı korunur: CV ve match rate review'dan, diller ilk üretimden.
- Numara yalnızca sheet yazımı başarılı olunca harcanır (`save_last_cv_no`), eski `run_scan` gibi.

### MCP sunucusu

- **stdout MCP protokolüne ayrılmıştır.** Loglar stderr'e ve `state/mcp.log`'a gider; `print` yok.
  `state/agent.log`'u poller döndürüyor, iki süreç aynı dosyayı döndürürse birbirini keser.
- Senkron araçlar `anyio.to_thread` ile işçi thread'lerinde çalışır. Playwright'ın sync API'si
  nesneleri oluşturan thread'e bağlıdır; bu yüzden `prepare_job` her çağrıda kendi `Scraper`'ını
  açıp kapatır (satır başına ~2 sn tarayıcı açılışı).
- Playwright (scraper/pipeline) **araç içinde, ihtiyaç anında** import edilir; mektup oturumu onu hiç
  yüklemez.

### Hook'lar

- `guard_secrets.py` (PreToolUse): `credentials/`, `.env`, `.env.bak*` ve `linkedin_state.json`
  yollarını reddeder. Yalnızca yol/komut alanlarını tarar (`file_path`, `path`, `pattern`,
  `command`…), Write/Edit içeriğini taramaz: bu dosyalardan **bahseden** bir belge yazmak erişim
  değildir. Bash komutunda tırnak içi metin (commit mesajı) atlanır; bedeli `cat ".env"` gibi tırnaklı
  bir yolun geçmesi — Read için `settings.json` deny kuralları ayrıca korur, başsız oturumda Bash
  zaten kapalı.
- `check_cv_output.py` (PostToolUse): yalnızca `cv_<no>_(analysis|review).md` için çalışır; CV'yi
  `.docx`'i üreten ayrıştırıcıyla okur. İşaretçiler, `### ` ile başlama, deneyim girdisi sayısı ve
  maddeleri, proje sayısı (= şablondaki yuva sayısı) ve her projenin `Tech:` satırı kontrol edilir.
  Bozuksa exit 2 → subagent düzeltip yeniden yazar. 192 eski analiz/review dosyasında yapısal yanlış
  alarm yok (yalnızca `<LANGUAGES>` özelliğinden önceki ≤274 numaralılarda o işaretçi eksik).

### Ölçülen maliyet (2026-10-23, Sonnet 5 medium)

Tek CV (cv-writer, CV 374'ün ilanı): ~6 dk, `total_cost_usd` ≈ $0.95 eşdeğer (abonelikten düşer,
faturalanmaz). Eski doğrudan API yolu ~2 dk / ~$0.16 idi; fark Claude Code'un oturum ek yükü
(sistem prompt'u, CLAUDE.md, skill dosyalarının okunması, alt agent bağlamı). Aday yokken `/cv-uret`
~19 sn / $0.14, önbellekteki bir mektup ~20 sn / $0.21. Kota için: CLAUDE.md'yi kısa tut, boş
turlarda agent başlatma (main.py zaten başlatmıyor).

## 2. Sheet ve CV hattının kuralları

- **"Google Sheet" aslında Drive'daki bir `.xlsx`.** `sheets.py` servis hesabıyla indirir, openpyxl
  ile düzenler ve aynı dosya kimliğinin üzerine yükler. openpyxl gidiş-dönüşü dropdown'ları düşürür;
  `sheets.py` her yazımda **veri doğrulama dropdown'larını yeniden kurar**. Dosya servis hesabı
  e-postasıyla Editor olarak paylaşılmalı.
- **CV için İKİ koşul: boş N *ve* `B == "Üretilecek"`.** N (CV No) "yapıldı mı?" sorusunu cevaplar
  (dolu = yapıldı); bu yüzden satırı silip aynı ilanı yeniden eklemek çalışır. 2026-08-10'dan beri
  `is_candidate` ayrıca B'nin `CV_TRIGGER_BASVURU_VALUES` (`{"Üretilecek"}`) içinde olmasını ister.
  **Neden:** "Ekle" ilan ilginç göründüğünde basılır, başvuru günler sonra olur ve ilan çoğu zaman
  kalkmış olur; ekleme anında üretim hiç başvurulmayan ilanlara CV üretiyordu. `config.
  CV_TRIGGER_BASVURU_VALUES` ile `sheets.DROPDOWNS["B"]` senkron kalmalı (dropdown her yazımda
  listeden yeniden kurulur). **Sheet'in kendisinde buton olamaz:** `.xlsx` olduğu için openpyxl her
  yazımda makroları düşürür, Google Sheets Office dosyalarında Apps Script çalıştırmaz ve Apps Script
  `localhost`'a ulaşamaz. `scripts/cv_uret.command` (Finder'da çift tık) bunun yerini tutar.
- **İlanı kalkmış işaretli satır `N = "Kalkmış"` (`EXPIRED_MARKER`) ile kapatılır, üretilmez.**
  `prepare_job` scrape'i üretimden önce ayrı bir `try` içinde yapar: hata → `write_info_only_row(row,
  {}, EXPIRED_MARKER)`, Claude çağrısı yok, CV numarası harcanmaz. Kaçış yolları: N'yi temizle + B'yi
  yeniden işaretle, ya da `run_once.py --row N --allow-staged` (panelin kaydettiği metinle üret).
- **İlan kimliği linkteki LinkedIn ilan no'sudur** (`_job_key`, `.../jobs/view/<id>`), M sütunu
  değil — M bir formül, openpyxl formül metnini döndürür. Link iki kez eklense de her ilan tek CV verir.
  `joblookup.linkedin_job_id()` aynı regex'in bilinçli kopyası (öneksiz no döner); ikisini senkron tut.
- **`CV_GENERATION` kapalı ("info-only"):** satırlar yine okunur, alanları (C/F/H/J/L) yazılır ve N'ye
  `"Yok"` işaretçisi konur; anahtar yeniden açılınca geriye dönük üretilmez. Bu yol model çağırmaz ve
  agent başlatmaz (`pipeline._process_info_only`, poller içinde).
- **`CV_REVIEW`** (varsayılan kapalı): her taslağa cv-reviewer ile ikinci uzman QA geçişi.
- **Sheet'e birden çok süreç yazar; `sheets.py` süreçler arası kilit tutar.** `sheet_lock()`
  (`state/sheet.lock` üzerinde `fcntl.flock`) her değiştiren metodun indir → düzenle → yükle
  döngüsünü `@_locked` ile sarar. Yazarlar: CV agent'ının MCP sunucusu, poller'ın info-only yolu ve
  özet API'si ("Ekle"). Kilit olmasa bir CV yazımı bitmeden başlayan bir ekleme o CV No'yu içermeyen
  bir çalışma kitabı yüklerdi. **`get_rows` bilerek kilitsiz** (saf okuma; Drive sürümleri atomik).
  `flock` yeniden girişli değil — bir `@_locked` metodu başka birinin içinden çağırma (120 sn sonra
  `SheetLockTimeout`).
- **Yeni satırlara tablonun biçimi kopyalanır (`_style_reference_row` / `_copy_row_style`).** openpyxl
  yeni bir hücreye yalnızca değer yazar; stil vermezsek satır varsayılan 11 punto çıkar ve E'ye
  yazılan tarih, "son satırın" (boş şablon satırının) `General` formatını alıp `46318` gibi bir seri
  numarası görünür (2026-10-23'te satır 781/782'de yaşandı). Biçim sabit sayılarla yazılmaz; en yakın
  "normal" satırdan (gerçek tarihli E + sayısal N) kopyalanır, çünkü tablonun kendi ayrıntıları var
  (B 7pt, C 9pt, Q 7pt, E `dd.MM.yyyy`). J köprüsüz kalır: şirket sayfasının URL'si ancak CV
  üretilirken scrape'ten gelir, o zaman `_link_font` uygulanır (köprü gibi görünüp tıklanmayan hücre
  yanıltıcı olurdu). Bozuk satırlar için `SheetsClient.reformat_rows([...])`.
- **`state/pending_jd/<job_id>.md` panelin kaydettiği ilan metni, isteğe bağlı yedek.** `/add-job`
  yazar (atomik, `PENDING_JD_MIN_CHARS = 200` tabanı). `_scrape_fields(row, scraper,
  allow_staged=True)` onu **yalnızca scrape hata verirse** okur, açıklama içeren bir `JobPage` kurar,
  uyarı loglar ve `record_failure("scrape_fallback", …)` çağırır. `allow_staged` her yolda varsayılan
  False: tetik başvuru anına taşındığından başarısız scrape büyük olasılıkla kalkmış ilan demek.
  `finalize_cv` sheet yazımından sonra dosyayı siler; `prune_pending_jd` 14 günden eskileri temizler.
- **Google Doc dışa aktarımı servis hesabıyla değil OAuth ile:** servis hesabı kişisel My Drive'da dosya
  oluşturamaz. `.docx` (`templates/cv_template.docx`'ten) Google Doc mimeType'ıyla yüklenir, Drive
  dönüştürür, sonra PDF olarak geri indirilir. Best-effort: hata kaydedilen Markdown CV'yi geri almaz.

### CV dürüstlük sözleşmesi

Kurallar `.claude/skills/ats-cv-kurallari/03-durustluk-sozlesmesi.md`'de, kullanıcının kendi kuralları
— gevşetme. Özet: **Hard-Tech** (kurulabilen adlandırılmış ürün: Redis, Kafka, AWS) kilitli —
`profile/cv_base.md` ya da `profile/projects.md`'de yoksa hiçbir biçimde CV'ye girmez. **Hard-Practice**
(ürün adı vermeyen pratik/nitelik: debugging, best practices, scalability) ve **Soft** serbestçe
örülür. Kalın ekleme tarz ya da işe içkin pratik kelimesi ekleyebilir; asla yeni teknoloji, alan,
ürün, bağlam ya da sonuç ekleyemez. **Kalın = `cv_base.md`'ye göre diff**, yalnızca Markdown'da;
`_strip_md` `.docx`/Doc/PDF'e geçirmez. Doğrulama: her kalın kısmı sil, kalan EXPERIENCE maddesi bir
`cv_base.md` maddesine indirgenmeli (ADIM 12/2b; script'le kontrol edilebilir). Bilinen boşluk: model
bazen bir *amaç yan cümlesi* kaçırır (`…global exception handling **to support efficient
troubleshooting**`); logging'in içkin özelliği olduğu için tolere edilir.

### Markdown ↔ .docx ayrıştırma tuzakları (üç kez canlıya çıktı)

"İncelediğin Markdown ≠ işverene giden PDF" hatası üç farklı yoldan geldi; `check_cv_output.py` hook'u
bunları artık yazım anında yakalıyor.

- **EXPERIENCE maddeleri:** `build_docx` her girdinin maddelerini sırayla doldurur (2026-07-16'ya kadar
  yalnızca "Intern" girdisi doldurulur, mevcut işin maddeleri şablonun donmuş metniyle giderdi).
  Girdi **başlıkları** bilerek doldurulmaz (şablon tarihi `Jun – Aug 2025` diye yazar).
  `_fill_bullets` her girdinin yuvasını bağımsız büyütür/küçültür.
- **Madde işareti `[*-]\s+` (`_BULLET_RE`), yalnızca `*` değil.** 2026-08-07'de bir editörün
  format-on-save'i (Prettier) `cv_base.md`'deki `*` listelerini `-` yaptı ve bütün maddeler
  ayrıştırmadan düştü. `.prettierignore` (çapasız kalıplar) ve `.vscode/settings.json` (`[markdown]`
  için formatOnSave kapalı) ek koruma. **`profile/`, `.claude/`, `prompts/` altındaki Markdown veridir:
  hiçbir biçimlendirici dokunmamalı.**
- **`parse_markdown_cv`'deki her yapısal test önce `**`'ı silmeli.** ADIM 8 bir projeyi takas edince
  bütün bloğu farklı olduğu için model başlığı ve `Tech:` satırını da kalın yazar (`**#### [..](..)**`,
  `**Tech: …**`). Ham metne çapalamak ikisini görünmez yaptı: takas edilen proje önceki projenin
  stack'iyle çıktı (175 CV'nin 15'i), cv_322'nin PDF'i API Hotel Project'i kaybetti. Çözüm `_heading()`
  ve `tech:` testinden önce silme; fazla yuvalar artık siliniyor. Etkilenen 16 PDF/Doc kaydedilmiş
  Markdown'dan `pipeline._export_google_doc(no, md)` ile yeniden kuruldu (model çağrısı yok).
- **CORE SKILLS satır sayısı değişkendir:** saf back-end ilanında `**Frontend:**` satırı çıkarılır;
  `_fill_core_skills()` yuvaları büyütür/küçültür ve kalın etiketi Markdown'dan alır.

### Yeniden üretim talimatı

`/cv-yenile <from> <to> [talimat]` (ya da `regenerate.py -i "…"`) talimatı
`regen_targets(instruction=…)` → `cv_output.extra_instruction_block` ile Türkçe "BU ÇALIŞMAYA ÖZEL
KULLANICI TALİMATI (EN YÜKSEK ÖNCELİK)" bloğuna çevrilir ve cv-writer'a (açıksa cv-reviewer'a) aynen
geçer. Seçim/yerleşim varsayılanlarını ezer, dürüstlük sözleşmesini ezmez. Talimat aralıktaki HER CV'ye
uygulanır; CV'ye özel bir değişiklik için `from == to` kullan.

## 3. Kullanıcının LinkedIn oturumunu otomatikleştirme

`scraper.py` LinkedIn'i yalnızca **herkese açık misafir görünümünde** okur. Kullanıcının LinkedIn
oturum çerezini (`linkedin_state.json`) hiçbir otomatik/başsız tarayıcıya yükleme: LinkedIn hesabı
işaretler ve bütün oturumları kapatır (2026-07'de haftalarca sürdü). `guard_secrets.py` hook'u bu
dosyaya erişimi engeller. LinkedIn'de aktif gezinirken `./scripts/start_api.sh` (yalnızca API, poller
yok) çalıştır.

## 4. Panel eklentisi + özet API'si

- **`extension/content.js`** paneli `linkedin.com`'a enjekte eder, ilan metnini çıkarır (yeni
  `/jobs/search-results` arayüzü hash'li sınıflar kullandığı için `collectRoots`/`deepQuery` ile açık
  shadow root'ları + aynı kökenli iframe'leri deler) ve `background.js` üzerinden backend'e gönderir.
  `/jobs/search-results` ve tek başına `/jobs/view/<id>` sayfalarını destekler. `DEBUG` bayrağı bütün
  `[JobSum] DIAG` çıktısını kapılar. "İncelendi" ve "Olabilir" iki bağımsız `makeMarkerStore`.
  - **LinkedIn'in kendi kapatma (X) butonu ilanı incelendi işaretler** (`aria-label` ile,
    `event.composedPath()` üzerinden — shadow root içindeki butonu da görür).
  - **Yeni arayüz kartı kendini yalnızca `componentkey="job-card-component-ref-<id>"` ile tanıtır**;
    `data-job-id` yok ve kartın içinde `/jobs/view/` linki yok. `cardFrom()`'un son çare link taraması,
    bir ata birden fazla ilan linki tuttuğu an durmalı.
  - **Açıklama yükleme zaman aşımı** (`DESC_LOAD_TIMEOUT_MS`, 12 sn): metin bulunamazsa Türkçe
    "kaydır + Yenile" ipucu ve koşulsuz bir DIAG dökümü.
  - **En uzun görünür metin sezgisi sol liste kartlarını atlar** (`LIST_CARD_SELECTOR`); tohum eşiği
    düşük (50), asıl koruma birleştirilmiş kapsayıcıdaki 300 karakter tabanı.
  - **`seenOnly`:** özetlenmeden listeden kapatılan ilan bir daha özetlenmez (model çağrısı yok);
    "Yenile" geçersiz kılar.
  - **Mektup görünümü** `showingCover` ile korunur (700 ms'lik `maybeUpdate` yoklaması ezmesin);
    `ensurePanel()` yeniden kurulumdan sonra mektup handler'larını yeniden bağlamalı; ilan değişince
    `exitCoverView()`. Kopyalama ayrı bir tıklama (`navigator.clipboard` canlı etkileşim ister).
- **`POST /add-job` ("Ekle")** link (K) + pozisyon (L) + şirket (J) ekler, N'yi boş bırakır.
  `_canonical_link()` gerekli çünkü `/jobs/search-results` URL'si `?currentJobId=<id>` biçiminde.
  Tekrar kontrolü `_find_job_row()` / `_LINK_INDEX`; ıskalamada bir kez zorla yeniler.
  **`_ADD_LOCK` (threading) dosya kilidine ek olarak gerekli** — FastAPI senkron uç noktaları thread
  havuzunda çalıştırır, çift tıklama iki isteği aynı anda kontrolden geçirebilir.
- **`POST /cover-letter` ("Mektup"):** dosya varsa döndürür; yoksa `cover_letter.get_or_create`
  `agent_runner.run_cover_letter` ile `/mektup`'u çalıştırır (~30-60 sn). `_COVER_LOCK` aynı anda iki
  mektup üretimini sıraya koyar. ilan no → CV No, 5 dakikalık `_sheet_snapshot()` ile; ıskalama
  404'ten önce bir kez yeniler ve önbelleğe alınmaz.
- **`summary_api.py` projede Anthropic API'yi doğrudan çağıran TEK yer.** Özet her ilan açılışında
  çalışır; bir agent oturumu (10-20 sn, kota) yerine Haiku (`SUMMARY_MODEL`) `temperature=0` ile
  ~2 sn. System prompt `prompts/ozet_sistem.md` (Türkçe), sonuç `JobSummary` şeması, düz JSON
  (structured outputs değil — 14 alanlı şema gramer derleme bütçesini aşıyordu).
  - **`fit_score` YALNIZCA zorunlu teknolojileri karşılaştırır, deneyimi/kıdemi tamamen yok sayar.**
    Profil = `profile/cv_base.md` + `profile/projects.md`.
  - **`stack` alternatif GRUPLARININ listesi:** `[["Python","Go","Rust"], ["Docker"]]`. Tek seçenek
    içinde `/` dil + framework'ü bağlar (`"Java / Spring Boot"`). `field_validator` düz listeyi sarar.
  - **`stack_known` sunucu doldurur, model değil.** `_profile_mentions()` yazım varyantlarıyla
    eşleştirir (`_SYNONYM_GROUPS`).
  - **Yeşil bandın altında (1-69) `fit_reason` Python'da kurulur** (`_annotate_stack`): yalnızca
    eksikler. 70 eşiği `content.js`'teki `renderFit` ile aynı — **ikisini birlikte değiştir**.
  - **Sonuç önbelleği** ilan no'suna göre, LRU, `state/summary_cache.json`'a yansıtılır.
    **`_CACHE_VERSION`'ı artır**: `prompts/ozet_sistem.md`, `JobSummary` şeması ya da aday profili
    değişince (şu an 12; Türkçe prompt'a geçişte artırıldı).
- **`summary_api` asla `pipeline`/`scraper`/`mcp_server` import etmemeli** (Playwright zinciri; API,
  kullanıcı LinkedIn'de gezinirken çalışan süreç). `joblookup.py` bu yüzden var. `cover_letter` →
  `agent_runner` sadece stdlib + config import eder. Kontrol komutu `CLAUDE.md`'de.

## 5. Mektuplar

- Mektup **`cv_<no>.md` + kayıtlı ilan metni + `profile/projects.md`**'ye dayanır. Dürüstlük
  sözleşmesi burada da geçerli: proje listesi yalnızca adayın kendi projelerine *ayrıntı* ekler;
  yeni işveren/görev/metrik/tarih, "familiar with" yumuşatması, kişisel projeyi iş deneyimi gibi
  sunmak yok.
- **İmza doldurulmuş bir şablon:** `SIGN_OFFS[lang]` agent'a verilir ve `save_letter` mektubun
  birebir onunla bitmesini kontrol eder (düzyazı kuralı zaman zaman yok sayılıyordu).
- **Dosyanın kendisi önbellektir:** `cover_letter_<no>_<lang>.md`; kimlik (iş, dil). `--force` /
  "Yeniden üret" tek yeniden üretim yolu. `cover_letter_dir`'de asla glob yapma — eski el yapımı
  dosyalar (`cover_letter_117_fs.docx`, No. 138'e kadar) aynı klasörde.
- **Yalnızca CV No ≥ 200** (altında `cv_<no>.md` / `job_description_<no>.md` saklanmadı).
- **Relocation cümlesi G (çalışma şekli) + F (şehir) okur, H değil.** Remote → cümle yok; ofisten/
  hibrit → F'nin şehriyle; G boş (~%39) → şehirsiz temel cümle. Türkçe mektuplarda gerçek yönelme eki
  (`_tr_dative`: İstanbul'a, Ankara'ya, İzmir'e). `ONSITE_WORK_MODES` `cv_output.py`'de, iki kural paylaşır.
- **Kayıt başlığı yalnızca diskte:** `<!-- cv_no: .. | lang: .. | model: .. | tarih -->`;
  `get_or_create` gövdeyi başlıksız döndürür.

## 6. Yapılandırma

Hepsi `.env` (bkz. `.env.example`). Önemliler: `ANTHROPIC_API_KEY` (yalnızca panel özeti),
`SPREADSHEET_ID`, `SHEET_NAME` (varsayılan `Sayfa1`), `CV_MODEL` / `CV_EFFORT` (CV agent'ları,
varsayılan `claude-sonnet-5` / `medium`), `COVER_LETTER_MODEL`, `SUMMARY_MODEL`, `CLAUDE_BIN`,
bayraklar `CV_GENERATION` / `CV_REVIEW` / `HUNTR_BOARD_URL`, `POLL_INTERVAL`. Çıktılar varsayılan
olarak `outputs/` altında (gitignore'da). `credentials/`, `state/`, `outputs/` git'e girmez.

Effort ölçümleri (eski API yolu, Sonnet 5): high ~$0.40, medium ~$0.16, low ~$0.11 / CV; ATS skoru
effort'la ters orantılı çıktı (low anahtar kelime doldurmaya meyilli). Bu yüzden toplu üretim
`medium`, önemli bir ilan için tek CV'yi `CV_EFFORT=high` ile `/cv-yenile` et.

**Huntr** (inert): `HUNTR_BOARD_URL` boş, `sync_huntr_to_sheet()` hiç çağrılmaz; `huntr.py` ve
`scripts/huntr_login.py` duruyor, board URL'si verilince yeniden açılır.
