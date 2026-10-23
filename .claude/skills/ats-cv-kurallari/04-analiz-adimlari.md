# ATS ANALİZ SÜRECİ

Aşağıdaki adımları sıkı sıkıya izle.

ÖNEMLİ KURAL:
Analizin tamamı için **YALNIZCA TEK BİR TABLO** oluşturmalısın.

Birden çok tablo üretme.

Bütün veriler tek bir **Ana Beceri Tablosu**'na konmalı ve analiz ilerledikçe güncellenmelidir.

---

# ADIM 1 — Anahtar Kelime Çıkarımı

**İLAN METNİ**'nden şunları çıkar:

En fazla:

- **20 Hard Skill** (Hard-Tech + Hard-Practice toplamı)
- **20 Soft Skill**

Her anahtar kelime için şunları belirle:

- Beceri türü — **Hard-Tech**, **Hard-Practice**, **Soft** türlerinden tam olarak biri (bkz.
  TANIMLAR; her hard anahtar kelimeye "kurabilir miyim?" testini uygula ve bir pratik terimini
  asla Hard-Tech diye dosyalama)
- İlan metnindeki frekansı

Frekans = anahtar kelimenin ilan metninde geçme sayısı.

Şu becerilere öncelik ver:

- birden çok kez geçenler
- teknik bölümlerde geçenler
- gereksinim bölümlerinde geçenler

Analiz tamamlanmadıysa henüz tablo oluşturma.
Bunun yerine çıkarılan bütün becerileri topla ve **Ana Beceri Tablosu** için hazırla.

---

# ADIM 2 — Anahtar Kelime Yoğunluğu

Çıkarılan her beceri için anahtar kelime yoğunluğunu hesapla.

Formül:

Anahtar Kelime Yoğunluğu = (Anahtar Kelime Sayısı / İlan Metnindeki Toplam Kelime) × 100

Yoğunluk değeri daha sonra **Ana Beceri Tablosu**'na eklenmelidir.

---

# ADIM 3 — Özgeçmiş Anahtar Kelime Analizi

**CV**'yi analiz et ve her beceri için şunları belirle:

- anahtar kelimenin var olup olmadığı
- CV'de kaç kez geçtiği

Eşleşme gücüne göre bir durum ata.

Durum kuralları:

- ✅ Güçlü Eşleşme → anahtar kelime yeterince geçiyor
- ⚠️ Zayıf Eşleşme → anahtar kelime geçiyor ama yetersiz
- ❌ Yok → anahtar kelime CV'de geçmiyor

---

# ADIM 4 — Ana Beceri Tablosu

Şimdi **toplanan bütün bilgiyi** içeren **TEK bir tablo** oluştur.

Başka tablo oluşturma.

Tablo çıkarılan bütün becerileri içermeli ve her ölçütü göstermelidir.

Gerekli yapı:

| Beceri | Tür | İlan Frekansı | CV Frekansı | Yoğunluk % | Durum |

Sütunların açıklaması:

Beceri → ilan metninden çıkarılan anahtar kelime
Tür → **Hard-Tech**, **Hard-Practice** ya da **Soft** (asla sadece "Hard" değil — eksik bir
      anahtar kelimenin bilerek mi dışarıda bırakıldığını yoksa eklenebilir mi olduğunu okuyana
      söyleyen şey alt türdür)
İlan Frekansı → anahtar kelimenin ilan metninde geçme sayısı
CV Frekansı → anahtar kelimenin CV'de geçme sayısı
Yoğunluk % → ilan metninden hesaplanan anahtar kelime yoğunluğu
Durum → ✅ Güçlü Eşleşme / ⚠️ Zayıf Eşleşme / ❌ Yok

Tabloyu şu sırayla sırala:

1. En yüksek İlan Frekansı
2. En yüksek Yoğunluk %

---

# ADIM 5 — ATS Puanlama Algoritması

ATS eşleşme skorunu hesapla.

Ağırlık modeli:

Hard Skill'ler (Hard-Tech + Hard-Practice) = %70
Soft Skill'ler = %30

Hesaplama adımları:

### Hard Skill Skoru

Hard-Tech ve Hard-Practice **tek** bir kovayı paylaşır — ayrı ağırlıklandırma.

Hard Skill Skoru =
(✅ Güçlü Eşleşme olan Hard-Tech + Hard-Practice beceri sayısı / Toplam Hard-Tech + Hard-Practice beceri) × 70

### Soft Skill Skoru

Soft Skill Skoru =
(✅ Güçlü Eşleşme olan Soft Skill sayısı / Toplam Soft Skill) × 30

### Nihai Eşleşme Skoru

ATS Eşleşme Skoru =
Hard Skill Skoru + Soft Skill Skoru

**Hesaplamanın tamamını adım adım** göster.

---

# ADIM 6 — Özgeçmiş Optimizasyon Stratejisi

Bkz. `03-durustluk-sozlesmesi.md` (kurallar 1–5, 3b, 4b). Bu adım dürüstlük sözleşmesidir;
ayrı dosyada durması önemini azaltmaz.

---

# ADIM 6.5 — ROL HEDEFLEME VE CORE SKILLS UYARLAMASI (KRİTİK)

Aday **üç tür ilana** başvuruyor. Önce bu İLAN METNİ'nin hangisine en yakın olduğuna karar ver,
sonra CV'yi — özellikle **CORE SKILLS** bloğunu ve Summary'yi — buna göre şekillendir. Rol hedefleme
**sadece vurguyu ve sırayı** değiştirir, asla doğruluğu değil: YALNIZCA adayın profilinde zaten
olan teknolojileri kullan (ADIM 6 kural 3).

- **Backend Developer** → Backend dilleri/framework'leri, API'ler, veritabanları, mimari ve DevOps
  ile başla. Front end'i geri plana at. **`Frontend:` satırını tamamen ÇIKAR** (saf back-end ilanı
  gibi davran).
- **Full-Stack Developer** → Backend ve frontend'i dengele. **`Frontend:` satırını TUT** ve adayın
  gerçekten sahip olduğu front-end teknolojilerini öne çıkar (React, Next.js, JavaScript, HTML, CSS,
  Tailwind CSS). Summary'yi full-stack olarak çerçevele.
- **AI Engineer** → **AI & LLM** satırıyla (OpenAI/Claude API'leri, LangChain, RAG, embeddings, vector
  search, AI agents, prompt engineering) ve AI/RAG projesiyle başla; backend satırını güçlü tut.
  `Frontend:` satırını yalnızca ilan front-end'e dönükse tut.

Her CORE SKILLS satırının içinde, ilanın vurguladığı teknolojiler önce gelecek şekilde yeniden
sırala. Rol istiyor diye profilde olmayan bir teknolojiyi asla ekleme (ADIM 6 kural 3). `Frontend:`
satırını tutma/çıkarma kuralının tam hali ÇIKTI BİÇİMİ bölümündedir (`05-kalin-ve-cikti-formati.md`)
— yukarıdaki role göre uygula.

---

# ADIM 7 ve ADIM 8

Bkz. `03-durustluk-sozlesmesi.md`.

---

# ADIM 9 — İşe Alımcı Okunabilirliği Optimizasyonu

İşe alımcı okunabilirliğini iyileştir.

Şu ilkeleri uygula.

### Güçlü Eylem Fiilleri

Örnekler:

- Developed
- Implemented
- Designed
- Architected
- Optimized
- Built

### Teknik Netlik

Her madde şu kalıbı izlemeli:

Eylem + Teknoloji + Sonuç

Örnek:

Developed REST APIs using NestJS and PostgreSQL for managing authentication and persistent data storage.

### Madde Optimizasyonu

Her madde:

- bir eylem fiiliyle başlamalı
- 1–2 teknoloji içermeli
- net bir teknik sonucu anlatmalı

### Summary Optimizasyonu

Summary:

- yüksek yoğunluklu anahtar kelimeler içermeli
- **en fazla 5 satır** olmalı
- adayın **hedef roldeki** uzmanlığını açıkça anlatmalı (backend / full-stack / AI — bkz. ADIM 6.5),
  varsayılan olarak backend değil
- o hedef rolün odağını yansıtmalı

---

# ADIM 11 — Nihai Çıktılar

Sonuçları şu sırayla ver.

---

## 1️⃣ Ana Beceri Tablosu

Şunları içeren **tek bir tablo** ver:

| Beceri | Tür | İlan Frekansı | CV Frekansı | Yoğunluk % | Durum |

Ek tabloya izin yok.

---

## 2️⃣ ATS Eşleşme Skoru

Puan hesaplamasının tamamını göster.

---

## 3️⃣ Optimize Edilmiş Özgeçmiş

Güncellenmiş CV'yi **Markdown formatında** ver.

Kurallar:

- madde işaretleri `*` olmalı
- CV **tek sayfa** kalmalı
- mümkün olduğunca orijinal yapıyı koru
- junior–orta seviye gerçekçiliğini koru

---

## 4️⃣ Yeni ATS Eşleşme Skoru

Optimizasyondan sonra eşleşme skorunu yeniden hesapla ve iyileşmeyi açıkla.
