"""Sistemin Drive'ında Google Doc oluşturabilmesi için tek seferlik OAuth girişi.

Ön koşul: Google Cloud Console'dan bir OAuth istemci kimliği ("Desktop app" türünde) indir
ve credentials/oauth_client.json olarak kaydet.

Kullanım:
    python scripts/google_login.py

Erişim izni vermen için bir tarayıcı açılır. Ortaya çıkan token (gözetimsiz kullanım için
yenileme token'ıyla) credentials/oauth_token.json'a kaydedilir.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from src.applyjobs.config import OAUTH_CLIENT_FILE, OAUTH_TOKEN_FILE  # noqa: E402
from src.applyjobs.drive_docs import SCOPES  # noqa: E402


def main() -> None:
    if not OAUTH_CLIENT_FILE.exists():
        raise SystemExit(
            f"Missing {OAUTH_CLIENT_FILE}.\n"
            f"Create an OAuth client ID (Desktop app) in Google Cloud Console, "
            f"download the JSON, and save it there."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CLIENT_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    OAUTH_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved OAuth token to {OAUTH_TOKEN_FILE}")


if __name__ == "__main__":
    main()
