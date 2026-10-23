"""LinkedIn İlan Özeti API'sini çalıştırır (tarayıcı eklentisinin backend'i).

Kullanım:
    python scripts/run_summary_api.py
    SUMMARY_API_PORT=8001 python scripts/run_summary_api.py

Eklenti API'yi varsayılan olarak http://localhost:8000'de bekler. Portu değiştirirsen
extension/background.js'i (BACKEND_BASE) ve manifest.json'u (host_permissions) da güncelle.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from src.applyjobs.reporting import setup_console_logging  # noqa: E402
from src.applyjobs.summary_api import app  # noqa: E402


def main() -> None:
    # uvicorn.run'dan önce: onun dictConfig'i var olan logger'lara dokunmaz; yani burada eklenen kök
    # handler hayatta kalır ve uygulamanın kendi satırları erişim logunun yanına düşer.
    setup_console_logging()
    port = int(os.getenv("SUMMARY_API_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
