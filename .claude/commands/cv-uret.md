---
description: Sheet'te Başvuru (B) = "Üretilecek" olan satırlar için CV üretir (orkestratör)
argument-hint: "[--row N] [--limit N] [--allow-staged]"
---

# /cv-uret — CV üretim orkestrasyonu

Bu çalışmanın **orkestratörüsün**. Argümanlar: `$ARGUMENTS`

Görevin: aday satırları cv-tools MCP araçlarıyla bulmak, her biri için CV'yi **cv-writer**
subagent'ına yazdırmak ve sonucu cv-tools ile kesinleştirmek.

**Sınırların:**
- CV'yi kendin YAZMA ve hiçbir dosyayı kendin düzenleme; yazma işi subagent'ların.
- Sheet'e, LinkedIn'e, Drive'a doğrudan dokunma; yalnızca `mcp__cv-tools__*` araçlarını kullan.
- CV numarası, "Kalkmış" işaretçisi ve sheet yazımı araçların işidir. Numarayı sen seçme, değiştirme;
  `prepare_job`'un verdiği numarayı aynen kullan.
- Satırları **sırayla** işle (paralel değil): numaralandırma ve sheet kilidi buna göre tasarlandı.

## Adım 0: Argümanları çöz

- `--row N` → `only_row = N`
- `--limit N` → `limit = N`
- `--allow-staged` → `allow_staged = true` (ilan okunamazsa panelin kaydettiği metinle üret;
  kullanıcının bilinçli istisnası)
- Başka bir şey yazıldıysa yok say.

## Adım 1: Adaylar

`mcp__cv-tools__cv_candidates(only_row, limit)` çağır.

- `cv_generation` false ise: "CV üretimi kapalı (CV_GENERATION=off)." yaz ve dur.
- `candidates` boşsa: "İşlenecek satır yok." yaz ve dur.

## Adım 2: Her aday için (sırayla)

**a. Hazırla:** `mcp__cv-tools__prepare_job(row, allow_staged)`.
- `status: "expired"` → ilan kalkmış; araç N="Kalkmış" yazdı. Bu satır için CV ÜRETME, kaydet,
  sonrakine geç.
- `status: "not_candidate"` ya da `"error"` → mesajı kaydet, sonrakine geç.
- `status: "ready"` → devam et.

**b. Yaz:** Agent aracıyla **cv-writer** subagent'ını çağır. Prompt'a şunları açık etiketlerle koy:
- `CV No: <cv_no>`
- `İLAN METNİ yolu: <job_description_path>`
- `Analiz dosyası yolu: <analysis_path>`
- `SUMMARY KAPANIŞ CÜMLESİ KURALI: <relocation_rule>` — metni **birebir** kopyala, özetleme
- Bu komutta KULLANICI TALİMATI yoktur.

**c. Denetle (sadece `cv_review` true ise):** Agent aracıyla **cv-reviewer**'ı çağır: CV No, İLAN
METNİ yolu, taslak yolu (= analiz dosyası yolu), review dosyası yolu (`review_path`) ve aynı
SUMMARY KAPANIŞ CÜMLESİ KURALI. Reviewer başarısız olursa sorun değil: `finalize_cv` ilk taslağı
kullanır.

**d. Kesinleştir:** `mcp__cv-tools__finalize_cv(row)`.
- `status: "done"` → CV No, match rate, PDF ve DOCX yolunu ve `pdf_warnings`'i kaydet. Uyarı
  CV'yi başarısız saymaz ve yeniden deneme gerektirmez; yalnızca raporlanır.
- `status: "error"` → mesajı kaydet. Numara harcanmadı; satır aday olarak kalır ve bir sonraki
  turda yeniden denenir. cv-writer analiz dosyasını yazamadıysa bu satır için onu en fazla BİR kez
  daha çağırıp `finalize_cv`'yi tekrarlayabilirsin.

Bir satırın hatası diğer satırları durdurmaz.

## Adım 3: Rapor

Türkçe, kısa:
- Üretilenler: `CV <no> ← satır <row> | match <oran> | <pdf yolu> | <docx yolu>`; `pdf_warnings`
  boş değilse altına `  ⚠ PDF kontrolü: <uyarılar, ; ile>`
- Kalkmışlar: `satır <row>`
- Hatalılar: `satır <row>: <mesaj>`

Son satır tam olarak şu biçimde olsun: `Scan complete: <X> generated, <Y> expired, <Z> failed.`
