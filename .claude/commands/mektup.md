---
description: Daha önce üretilmiş bir CV için istendiğinde cover letter yazar (EN ya da TR)
argument-hint: "<cv_no> [en|tr] [--force]"
---

# /mektup — cover letter orkestrasyonu

Bu çalışmanın **orkestratörüsün**. Argümanlar: `$ARGUMENTS`

Mektuplar yalnızca istendiğinde üretilir (her başvuru mektup istemez). Bir mektup (CV No, dil)
çifti için bir kez üretilir; **dosyanın kendisi önbellektir**. `--force` olmadan var olan mektubu
asla yeniden üretme.

**Sınırların:** mektubu kendin yazma; **cover-letter-writer** subagent'ına yazdırırsın. Dosyalara ve
sheet'e doğrudan dokunma.

## Adım 0: Argümanları çöz

- İlk sayı `cv_no` (zorunlu; yoksa kullanımı yaz ve dur).
- `en` ya da `tr` → `lang` (varsayılan `en`).
- `--force` → `force = true`.

## Adım 1: Bağlam

`mcp__cv-tools__cover_letter_context(cv_no, lang, force)` çağır.

- `status: "exists"` → mektup zaten var: `text`'i olduğu gibi yaz ve dur. Model çağrısı yapma.
- `status: "error"` → `message`'ı olduğu gibi yaz ve dur (ör. CV yok, ilan metni yok, şirket boş).
- `status: "ready"` → devam et.

## Adım 2: Yaz

Agent aracıyla **cover-letter-writer**'ı çağır ve `cover_letter_context` çıktısındaki alanların
HEPSİNİ (`cv_no`, `lang`, `language`, `company`, `job_title`, `cv_path`, `job_description_path`,
`projects_path`, `relocation_rule`, `sign_off`) etiketleriyle, `relocation_rule` ve `sign_off`'u
**birebir** kopyalayarak prompt'a koy.

## Adım 3: Rapor

Subagent'ın dönüşüne göre tek satır: `Mektup kaydedildi → <path>` ya da hatanın nedeni.
