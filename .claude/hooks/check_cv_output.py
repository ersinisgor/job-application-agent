"""PostToolUse hook'u: cv-writer / cv-reviewer'ın yazdığı CV'yi, .docx'i üreten ayrıştırıcıyla
okuyup bozuksa agent'a hemen geri bildirir.

Neden var: "Markdown'da gördüğün ≠ işverene giden PDF" hatası üç kez canlıya çıktı (madde
işareti `-` olunca bütün maddeler kayboldu; `**###` başlıkları okunmadı; takas edilen projenin
`Tech:` satırı kaçtı). Her seferinde .docx sessizce şablonun donmuş metniyle çıktı. Bu hook aynı
ayrıştırıcıyı (cv_output + docx_builder) çalıştırır; sorun varsa çıkış kodu 2 ile agent'a
söyler, agent dosyayı düzeltip yeniden yazar. Format değişmedi, sadece kontrol öne alındı.

Sadece outputs/.../cv_<no>_analysis.md ve cv_<no>_review.md dosyalarına bakar.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_TARGET = re.compile(r"cv_\d+_(analysis|review)\.md$")


def _problems(text: str, is_review: bool) -> list[str]:
    from src.applyjobs import cv_output, docx_builder
    from src.applyjobs.config import CV_BASE_FILE, PROJECTS_LIST_FILE

    problems: list[str] = []
    if "<CV_START>" not in text or "<CV_END>" not in text:
        return ["<CV_START> / <CV_END> işaretçileri yok — CV dosyadan çıkarılamaz."]
    cv_md = cv_output.extract_cv(text)
    if not cv_md.startswith("### "):
        problems.append(
            "CV `### ` ile başlayan bir bölüm başlığıyla başlamıyor (ilk satır MEVCUT CV'deki gibi "
            "`### HEADLINE` olmalı)."
        )
    if re.search(r"<MATCH_RATE>\s*\d+(?:\.\d+)?\s*</MATCH_RATE>", text) is None:
        problems.append("<MATCH_RATE>sayı</MATCH_RATE> işaretçisi yok ya da sayı değil.")
    if not is_review and "<LANGUAGES>" not in text:
        problems.append("<LANGUAGES>…</LANGUAGES> işaretçisi yok (dil yoksa boş bırak ama işaretçiyi yaz).")

    base_md = CV_BASE_FILE.read_text(encoding="utf-8")
    base = docx_builder.parse_markdown_cv(base_md)
    cv = docx_builder.parse_markdown_cv(cv_md)
    # MEVCUT CV HEADLINE taşıyorsa (2026-10-23'ten beri) yazılan CV de taşımalı. Eski dosyalarda
    # bölüm yok; o zaman cv_base de taşımıyorsa kontrol atlanır.
    if base["headline"]:
        profile = base_md + "\n" + PROJECTS_LIST_FILE.read_text(encoding="utf-8")
        problems += cv_output.headline_problems(cv["headline"], profile)
    if not cv["summary"]:
        problems.append("SUMMARY okunamadı.")
    if not cv["core_skills"]:
        problems.append("CORE SKILLS satırları okunamadı.")
    if len(cv["experience"]) != len(base["experience"]):
        problems.append(
            f"EXPERIENCE'ta {len(cv['experience'])} girdi okundu, MEVCUT CV'de "
            f"{len(base['experience'])} var (`####` başlıkları korunmalı)."
        )
    for entry in cv["experience"]:
        if not entry["bullets"]:
            problems.append(f"EXPERIENCE girdisinde madde okunamadı: {entry['title']!r} (`* ` kullan).")
    if len(cv["projects"]) != len(base["projects"]):
        problems.append(
            f"SELECTED PROJECTS'te {len(cv['projects'])} proje okundu, şablonda "
            f"{len(base['projects'])} yuva var (proje takas edilir, sayı değişmez; başlık "
            "`#### [Title](url)` biçiminde olmalı)."
        )
    for p in cv["projects"]:
        if not p["bullets"]:
            problems.append(f"Projede madde okunamadı: {p['title']!r}.")
        if not p["tech"]:
            problems.append(f"Projenin `Tech:` satırı okunamadı: {p['title']!r}.")
    if re.search(r"^---\s*$", cv_md, re.MULTILINE):
        problems.append("CV'de yatay çizgi (`---`) var; orijinal yapıda yok.")
    return problems


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path_str = (event.get("tool_input") or {}).get("file_path", "")
    m = _TARGET.search(path_str or "")
    if not m:
        return 0
    path = Path(path_str)
    if not path.exists():
        return 0
    problems = _problems(path.read_text(encoding="utf-8"), is_review=m.group(1) == "review")
    if problems:
        print(
            f"{path.name} doğrulanamadı — .docx/PDF bu haliyle yanlış çıkar. Düzeltip dosyayı "
            "yeniden yaz:\n- " + "\n- ".join(problems),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
