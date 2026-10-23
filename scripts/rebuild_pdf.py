"""Kayıtlı Markdown CV'lerden .docx + Google Doc + PDF'i yeniden basar; model çağrısı yok.

Şablon değişince (ya da eski tasarıma dönünce) var olan CV'leri yeni görünüme taşımak için:
pipeline._export_google_doc ile aynı yol. Aynı adlı Google Doc güncellenir (eski hâli Drive'ın
sürüm geçmişinde kalır); yerel cv_<no>.pdf ve cv_<no>.docx üzerine yazılır. Sheet'e dokunulmaz.
Şablon CV_TEMPLATE ile seçilir (bkz. .env.example).

Kullanım:
    python scripts/rebuild_pdf.py --from 560 --to 560
    CV_TEMPLATE=cv_template_eski.docx python scripts/rebuild_pdf.py --from 560 --to 565
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.applyjobs import pipeline  # noqa: E402
from src.applyjobs.config import CV_TEMPLATE_FILE, settings  # noqa: E402
from src.applyjobs.reporting import setup_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild CV docx/Doc/PDF from saved Markdown.")
    parser.add_argument("--from", dest="start", type=int, required=True, help="First CV No.")
    parser.add_argument("--to", dest="end", type=int, required=True, help="Last CV No.")
    args = parser.parse_args()

    setup_logging()
    if not CV_TEMPLATE_FILE.exists():
        print(f"Şablon bulunamadı: {CV_TEMPLATE_FILE}", file=sys.stderr)
        return 2
    print(f"Şablon: {CV_TEMPLATE_FILE.name}")

    rebuilt = failed = 0
    for cv_no in range(args.start, args.end + 1):
        md = settings.markdown_dir / f"cv_{cv_no}.md"
        if not md.exists():
            continue
        pdf = settings.pdf_dir / f"cv_{cv_no}.pdf"
        before = pdf.stat().st_mtime_ns if pdf.exists() else None
        warnings = pipeline._export_google_doc(cv_no, md.read_text(encoding="utf-8"))
        # Dışa aktarım başarısızsa PDF yazılmaz: yazılıp yazılmadığı tek güvenilir işaret.
        ok = pdf.exists() and pdf.stat().st_mtime_ns != before
        rebuilt += ok
        failed += not ok
        print(f"cv_{cv_no}: {'tamam' if ok else 'BAŞARISIZ'}")
        for w in warnings:
            print(f"  ⚠ {w}")
    print(f"{rebuilt} CV yeniden basıldı, {failed} başarısız.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
