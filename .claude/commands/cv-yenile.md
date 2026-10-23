---
description: Var olan CV'leri (CV No aralığı) kaydedilmiş ilan metinlerinden yeniden üretir, isteğe bağlı talimatla
argument-hint: "<from> <to> [talimat...]"
---

# /cv-yenile — CV yeniden üretim orkestrasyonu

Bu çalışmanın **orkestratörüsün**. Argümanlar: `$ARGUMENTS`

Kaydedilmiş ilan metinlerinden (yeniden okuma yok) bir CV No aralığını aynı numaralarla yeniden
ürettirirsin: `cv_<no>.md` ve analiz dosyası üzerine yazılır, aynı adlı Google Doc güncellenir, PDF
yeniden indirilir ve Match Rate (P) yenilenir. Diğer sheet sütunlarına dokunulmaz.

**Sınırların:** CV'yi kendin yazma, dosya düzenleme, sheet'e doğrudan dokunma; yalnızca
`mcp__cv-tools__*` araçlarını ve subagent'ları kullan. Hedefleri sırayla işle.

## Adım 0: Argümanları çöz

- İlk sayı `from`, ikinci sayı `to`. İkisi de yoksa ya da sayı değilse: kullanımı yaz
  (`/cv-yenile <from> <to> [talimat]`) ve dur.
- Geri kalan metnin tamamı (varsa) **talimat**tır. Olduğu gibi al; yorumlama, çevirme.

## Adım 1: Hedefler

`mcp__cv-tools__regen_targets(start=from, end=to, instruction=<talimat ya da "">)` çağır.

- `targets` boşsa: "Bu aralıkta CV No'su olan satır yok." yaz ve dur.
- `status: "missing_jd"` olan hedefleri kaydet ve atla (ilan metni hiç saklanmamış — eski CV'ler).

## Adım 2: Her `ready` hedef için (sırayla)

**a. Yaz:** Agent aracıyla **cv-writer**'ı çağır. Prompt'a açık etiketlerle:
- `CV No`, `İLAN METNİ yolu` (= `job_description_path`), `Analiz dosyası yolu` (= `analysis_path`)
- `SUMMARY KAPANIŞ CÜMLESİ KURALI: <relocation_rule>` — birebir
- `instruction_block` boş değilse: başına `KULLANICI TALİMATI bloğu:` yazıp bloğu **AYNEN, tek
  harfini değiştirmeden** ekle. Talimat seçim/yerleşim varsayılanlarını ezer ama dürüstlük
  sözleşmesini ezmez — eklenen her proje/beceri `profile/projects.md` ya da `profile/cv_base.md`'de
  olmalı.

**b. Denetle (sadece `cv_review` true ise):** **cv-reviewer**'ı çağır (taslak = analiz dosyası,
`review_path`, aynı kural ve aynı talimat bloğu).

**c. Kesinleştir:** `mcp__cv-tools__finalize_regen(cv_no)`. `error` dönerse mesajı kaydet ve
sonrakine geç.

## Adım 3: Rapor

Türkçe, kısa: yeniden üretilen her CV için `CV <no> | match <oran>`, atlananlar ve hatalar.
Son satır: `Regenerated <X> CV(s), <Z> failed.`
