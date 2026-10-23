"""Kayıtlı CV PDF'lerinin metin katmanını Markdown CV'lerine ve ATS kurallarına karşı denetler.

Model çağrısı ve Drive erişimi yok: yalnızca outputs/cv/pdf/cv_<no>.pdf ile
outputs/cv/markdown/cv_<no>.md okunur (src/applyjobs/pdf_check.py). Hata = gerçek kusur (içerik
eşliği, sayfa sayısı…); ATS = şablondan gelen biçim riski. ATS düzeltmeleri öncesinin şablonuyla
basılmış PDF'ler ATS uyarılarını bilerek verir.

Kullanım:
    python scripts/check_pdfs.py --from 559 --to 559
    python scripts/check_pdfs.py --from 200 --to 559 --errors-only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.applyjobs import pdf_check  # noqa: E402
from src.applyjobs.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check saved CV PDFs' text layer.")
    parser.add_argument("--from", dest="start", type=int, required=True, help="First CV No.")
    parser.add_argument("--to", dest="end", type=int, required=True, help="Last CV No.")
    parser.add_argument("--errors-only", action="store_true", help="Hide ATS format warnings.")
    args = parser.parse_args()

    checked = with_errors = with_ats = 0
    for cv_no in range(args.start, args.end + 1):
        pdf = settings.pdf_dir / f"cv_{cv_no}.pdf"
        md = settings.markdown_dir / f"cv_{cv_no}.md"
        if not (pdf.exists() and md.exists()):
            continue
        checked += 1
        result = pdf_check.check_cv_pdf(pdf, md.read_text(encoding="utf-8"))
        with_errors += bool(result.errors)
        with_ats += bool(result.ats)
        shown = result.errors if args.errors_only else result.messages()
        if shown:
            print(f"cv_{cv_no}:")
            for msg in shown:
                print(f"  - {msg}")
    print(f"{checked} PDF denetlendi: {with_errors} hatalı, {with_ats} ATS uyarılı.")
    return 1 if with_errors else 0


if __name__ == "__main__":
    sys.exit(main())
