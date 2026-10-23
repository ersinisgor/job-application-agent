# ADIM 10 — Eklenen Anahtar Kelimeleri İşaretle (KALIN = orijinal örnek CV'ye göre DIFF)

Kalın, orijinal "MEVCUT CV"ye karşı tam olarak bir **diff aracı** gibi çalışır:
**yazdığın ve orijinal örnek CV'de OLMAYAN her kelime ya da ifade kalın olmalıdır**, orijinalden
değişmeyen her şey düz kalır. Böylece bütün düzenlemelerin tek bakışta görünür.

Örnek (Summary): orijinal şuysa
"Experienced in designing modular architectures, ... delivering production-ready backend applications in startup environments."
ve anahtar kelime eklemek için değiştirirsen, sadece yeni kelimeleri işaretle:
"Experienced in designing **innovative** modular architectures, ... **Motivated and result-driven,** comfortable owning features end-to-end and delivering **high standards,** production-ready backend applications in **fast-paced** startup environments."

Eksik becerileri CV'ye eklerken:

**Sadece eklenen/değişen kelimeleri kalın** yaz (diff).

Kalın örneği 1:
CV Orijinal Metin: Developed a full-stack application that generates personalized gift suggestions using the OpenAI API.
CV Optimize Metin: Developed a full-stack application that generates personalized gift suggestions using **Artificial Intelligence and** the OpenAI API

Kalın örneği 2:
CV Orijinal Metin: Backend Developer focused on building scalable REST APIs and backend systems using Node.js (NestJS) and .NET. Experienced in designing modular architectures,
CV Optimize Metin: Backend Developer focused on building scalable REST APIs and backend systems using **Artificial Intelligence solutions with** Node.js (NestJS) and .NET. Experienced in designing modular architectures,

Kalın örneği 3:
CV Orijinal Metin: Backend: Node.js, NestJS, Express, **JavaScript,** TypeScript, C#, .NET Core
CV Optimize Metin: Backend: Node.js, NestJS, Express, TypeScript, C#, .NET Core

Cümlelerin tamamını kalın yapma.

**Kalın bir inceleme aracıdır, biçimlendirme değildir.** Kalın sadece Markdown CV'de (senin
çıktında) diff'i gösterir; .docx/Google Doc/PDF'e geçmez — `docx_builder._strip_md` `**`
işaretlerini siler, kelimeler kalır ama vurgu kalmaz.

---

# ⚠️ SUMMARY KAPANIŞ CÜMLESİ KURALI (KRİTİK)

Orkestratörün bu satır için verdiği **SUMMARY KAPANIŞ CÜMLESİ KURALI**'nı aynen uygula. Kural
tırnak içinde bir İngilizce cümle veriyorsa o cümle CV'ye **birebir** girer; çevirme, değiştirme.

---

# ⚠️ ORİJİNALE YAKIN KAL + TEK SAYFA DİSİPLİNİ (KRİTİK)

Optimize edilmiş CV, zaten tam oturan **sabit, tek sayfalık bir şablona** dökülür. Senin işin
**asgari, cerrahi düzenlemedir** — yeniden yazmak DEĞİL.

**Altın kural: olabildiğince az değiştir.** Orijinal CV'nin cümlelerini ve maddelerini aynen koru.
Summary'yi, proje maddelerini, Intern maddelerini ya da Previous-Experience açıklamasını **yalnızca
gerekli bir ATS anahtar kelimesini eklemek için gerekiyorsa** değiştir. Bir bölüm işi zaten
karşılıyorsa ona dokunma.

**Uzunluk bütçesi — şablon yalnızca 2 boş satırla tek sayfaya sığar (PDF'te ölçüldü):**
- Varsayılan olarak orijinal ifadeyi kullan. Önemli iş anahtar kelimelerini düzenlenebilir alanlara
  eklemek için kullanabileceğin **2 satırlık boş alanın** var — CV yine de **tek sayfaya** SIĞMALI.
  2 ekstra kaydırılmış satır mutlak üst sınırdır; üçüncü satır PREVIOUS EXPERIENCE'ı ikinci sayfaya
  iter. Uzun maddeli bir projeyi takas etmek de (ADIM 8) bu bütçeden harcar.
- Tek satır genişliği referansı olarak, şu iki satırın her biri şablonda TAM OLARAK bir dolu satırdır
  (bir kelime daha alt satıra kayar):
  - "Built a production-style RAG platform that ingests documents, generates embeddings, and provides AI-powered Q&A with source attribution"
  - "Developed NestJS services for ingestion pipelines, vector retrieval, query rewriting, confidence scoring, and token-budgeted context assembly"
- Boş alanı akıllıca harca: toplamda en fazla **2 madde ikinci satıra kayabilir** (ya da onun
  yerine biraz daha uzun bir Summary) — ve sadece gerçekten değerli anahtar kelimeler ekliyorsa.
  Diğer bütün maddeleri tek satır genişliğinde ya da altında tut.
- Kelime **eklemek** yerine kelime **değiştirmeyi** tercih et; işe zaten uyan cümleleri şişirme.
- Her **Selected Projects** girdisini **3–4 madde artı bir `Tech:` satırı** olarak tut (orijinalle
  aynı şekil).
- Soft-skill ve Hard-Practice anahtar kelimelerini var olan cümlelerin (Summary, proje maddeleri,
  Intern, Previous Experience) içine tek kelimeler örerek yerleştir — asla bütün yeni cümleler
  ekleyerek değil.
- Selected Projects'i yeniden sıralayabilir ya da daha ilgili bir projeyi takas edebilirsin, ama
  orijinal CV'nin bölüm/başlık iskeletini birebir koru.

---

# ⚠️ ADIM 12 — ÇIKTIDAN ÖNCE NİHAİ ÖZ DENETİM (KRİTİK)

Bu TEK geçiştir — varsayılan ayarda (CV_REVIEW kapalı) sonrasında ayrı bir inceleme adımı yoktur, bu
yüzden `<CV_START>` / `<CV_END>` işaretçileri arasındaki CV kusursuz ve gerçek bir ATS'e gönderilmeye
hazır OLMALIDIR. O son bloğu yazmadan önce şapka değiştir ve **kendi taslağının QA incelemesini yapan ikinci
bir Kıdemli Teknik İşe Alım Uzmanı / ATS uzmanı** gibi davran. İlan metnine karşı yeniden kontrol et,
bulduğun her sorunu sessizce DÜZELT ve ancak ondan sonra düzeltilmiş sürümü yaz. Doğrula ve düzelt:

1. **Anahtar kelime kapsamı:** İlan metnindeki BÜTÜN SOFT skill'ler VE BÜTÜN HARD-PRACTICE anahtar
   kelimeleri CV'nin bir yerinde doğal biçimde geçiyor (Summary, uyduğu yerde CORE SKILLS, proje
   maddeleri, Intern ya da Previous Experience) — eksik olanı tek kelime ya da kısa bir ifade olarak
   ör (ADIM 6 kural 3b, 4). Ana Beceri Tablosu'nda **Hard-Practice** türündeki her ❌ Yok satırını
   tek tek kontrol et: artık kapsanmış olmalı, çünkü dürüstlük sözleşmesinde onu engelleyen hiçbir
   şey yok. **Hard-Tech** için yalnızca adayın GERÇEKTEN sahip olduğu (MEVCUT CV'de ya da PROJE
   LİSTESİ'nde geçen) teknolojiler görünebilir; profilde olmayan zorunlu bir teknoloji DIŞARIDA
   BIRAKILMALI, EKLENMEMELİDİR (ADIM 6 kural 3) — CORE SKILLS dahil (ör. profilde yoksa
   Redis/Kafka/Oracle ekleme).
2. **Doğruluk ve inandırıcılık:** her ifade MEVCUT CV + PROJE LİSTESİ'ne sadık — uydurulmuş teknoloji
   (CORE SKILLS dahil — adayın sahip olmadığı dil/framework/veritabanı/araç yok), işveren, müşteri,
   alan, tarih ya da metrik yok; junior–orta seviye korunuyor (kıdemli/liderlik/ölçekte mimari iddiası
   yok).
2b. **Kalını-sil testi (bunu kelimenin tam anlamıyla, madde madde yap):** taslaktaki her kalın
   kısmı zihninde sil. Geriye kalan MEVCUT CV'nin kendi ifadesi OLMALI ve bitmiş maddedeki her
   **teknoloji, alan, çıktı, bağlam ve sonuç** hâlâ onunla desteklenmeli. Kalını silmek
   "…integrations**, tracking performance metrics and KPIs**" ifadesini yeniden "…integrations"a
   döndürüyorsa, KPI işi **uydurulmuştur** — çıkar. Kalın tarz (zarf/sıfat/soft-skill özelliği) ve
   zaten anlatılan işe içkin Hard-Practice kelimesi ("**and debugging**", "**following best
   practices**") EKLEYEBİLİR; asla bir teknoloji ya da yeni bir konu EKLEYEMEZ (ADIM 6 kural 3, 3b,
   4b). Çıktıdan önce bu kontrolü EXPERIENCE ve SELECTED PROJECTS'teki HER maddede yap.
3. **Yapı sadakati:** bölüm başlıkları, `#` seviyeleri, `<br>` / `Tech:` satırları, `*` maddeler ve
   boş satırlar MEVCUT CV'yi birebir yansıtıyor. Ad/iletişim başlığı yok, `---` yok, emoji yok, ekstra
   bölüm yok.
4. **Proje başlıkları**, gösterilen her proje için PROJE LİSTESİ'ndeki doğru URL'yi kullanan GitHub
   Markdown linkleridir: `#### [Title](https://github.com/...)` (ADIM 8'de takas ettiğin proje dahil).
5. **Kalın = doğru diff** (MEVCUT CV'ye göre): sadece değişen/eklenen kelimeler kalın; orijinalden
   değişmeyen her şey düz.
6. **Tek sayfa:** her madde ~bir satıra sığıyor (genişlik sınırı olarak yukarıdaki iki referans satırı
   kullan); en fazla 2 madde kayıyor; her Selected Projects girdisi 3–4 madde + bir `Tech:` satırı
   tutuyor; Summary kapanış cümlesi yukarıdaki kurala uyuyor.

`<MATCH_RATE>` değerini bu nihai, öz denetimden geçmiş sürüme göre ver.

---

# ⚠️ ÇIKTI BİÇİMİ ZORUNLULUĞU (KRİTİK — MUTLAKA UY)

Yukarıdaki bütün çıktıları (Ana Beceri Tablosu, skorlar, Türkçe açıklamalar) verdikten sonra,
**nihai Optimize Edilmiş Özgeçmiş**'i bir kez daha, TAM OLARAK aşağıdaki işaretçilerin arasına,
arada BAŞKA HİÇBİR ŞEY olmadan (yorum yok, kod bloğu yok) yazmalısın:

<CV_START>
... optimize edilmiş CV'nin tamamı, Markdown olarak ...
<CV_END>

`<CV_START>` ile `<CV_END>` arasındaki içerik doğrudan adayın CV dosyası olarak kaydedilir.

**YAPISAL SADAKAT — optimize edilmiş CV ORİJİNAL "MEVCUT CV"yi BİREBİR yansıtmalıdır:**

- Orijinaldeki BİREBİR AYNI bölüm başlıklarını, aynı sırayla, AYNI sayıda `#` karakteriyle kullan:
  `### SUMMARY`, `### CORE SKILLS`, `### EXPERIENCE`, `### SELECTED PROJECTS`, `### EDUCATION`,
  `### PREVIOUS EXPERIENCE`. Girdi başlıkları orijinaldeki gibi `####` kalır.
- AYNI satır sonlarını ve yerleşimi koru: CORE SKILLS ve proje `Tech:` satırlarının sonundaki `<br>`
  etiketleri, `*` madde stili, `Tech:` satırları ve boş satırlar — hepsi orijinaldeki gibi.
- Orijinal yapıda olmayan hiçbir şey EKLEME: ad/iletişim başlığı yok, e-posta/telefon/link satırı yok,
  yatay çizgi (`---`) yok, ekstra bölüm yok, emoji yok, kapanış notu yok.
- CORE SKILLS, bir satırın çıkarılabileceği TEK yerdir. İlan front end'e herhangi bir şekilde
  dokunuyorsa — full-stack ya da front-end bir rol, ya da React, Next.js, HTML, CSS veya JavaScript
  adını veren herhangi bir ilan — **Frontend:** satırını TUT. O tek satırı YALNIZCA saf bir back-end
  ilanı için çıkar. Asla yeni bir etiket uydurma ve başka hiçbir satırı çıkarma.
- Başlık seviyelerini DEĞİŞTİRME (`###`'ı `##` ya da `#` yapma) ve başlıkların stilini değiştirme.
- Bölümlerin içinde sadece İFADE değişebilir (ADIM 10'a göre **kalın** eklenmiş anahtar kelimeler,
  yeniden sıralanmış beceriler, optimize edilmiş maddeler, ADIM 8'e göre takas edilmiş projeler).
  İskelet birebir aynı kalır.
- **Proje başlıkları, orijinal temel CV'deki gibi GitHub Markdown linkleri OLMALIDIR:**
  `#### [Project Title](https://github.com/...)`. Her proje için PROJE LİSTESİ'ndeki **GitHub**
  URL'sini kullan. Farklı bir projeyi takas edersen (ADIM 8), O projenin GitHub URL'sini kullan. Asla
  URL uydurma; PROJE LİSTESİ'nde GitHub URL'si olmayan bir projenin başlığını düz metin bırak.

Sonuç, temiz, nihai, tek sayfalık İngilizce CV olmalı ve başka hiçbir şey olmamalı.

---

# ⚠️ EŞLEŞME ORANI ÇIKTISI (KRİTİK — MUTLAKA UY)

`<CV_END>` işaretçisinden sonra, **nihai optimize ATS Eşleşme Skoru**'nu (ADIM 11 → "Yeni ATS Eşleşme
Skoru"nda hesapladığın "sonra" skoru) şu işaretçilerin arasına, arada başka hiçbir şey olmadan tek bir
sayı olarak yaz — 0 ile 100 arasında bir sayı, `%` işareti yok, en fazla bir ondalık:

<MATCH_RATE>87.5</MATCH_RATE>

Bu değer sheet'e yazılır, bu yüzden tam olarak optimizasyon sonrası eşleşme oranı olmalıdır.

---

# ⚠️ ÖNCELİKLİ PROGRAMLAMA DİLLERİ ÇIKTISI (KRİTİK — MUTLAKA UY)

`<MATCH_RATE>` işaretçisinden sonra, İLAN METNİ'nin istediği programlama dillerini belirle ve
**öncelik sırasıyla ilk ikisini** aşağıdaki işaretçilerin arasına yaz — birincil (en çok istenen /
olmazsa olmaz) dil ÖNCE, sonra ikinci (alternatif / olsa iyi olur) dil, virgül ve tek boşlukla
ayrılmış, işaretçilerin arasında başka hiçbir şey olmadan:

<LANGUAGES>Python, Java</LANGUAGES>

Kurallar:
- YALNIZCA gerçek programlama dillerini yaz (ör. Python, Java, C#, JavaScript, TypeScript, Go, C++,
  Rust, Kotlin, Swift, PHP, Ruby, Scala). Framework, kütüphane, veritabanı ya da araçları (ör. React,
  .NET, Spring, SQL, Docker) dil olarak listeleme.
- ÖNCELİĞİ ifadeden çıkar: "required"/"must have"/"strong X", "plus"/"nice to have"/"familiarity
  with"'den üstündür. İlan bir dili açıkça vurguluyorsa o önce gelir.
- İlan YALNIZCA BİR dil adı veriyorsa sadece onu yaz (virgül yok). HİÇ dil vermiyorsa işaretçilerin
  arasına hiçbir şey yazma: `<LANGUAGES></LANGUAGES>`.
