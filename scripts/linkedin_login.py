"""Tek seferlik yardımcı (ARTIK KULLANILMIYOR): gerçek bir tarayıcı açar, kullanıcı LinkedIn'e
giriş yapar, sonra oturumu (çerezler + local storage) kaydeder.

UYARI: bu dosyanın ürettiği oturumu hiçbir otomatik tarayıcıya bağlama. Bir kez bağlandı ve
LinkedIn hesabı haftalarca bütün oturumları kapattı (bkz. scraper.py). Scraper yalnızca
misafir görünümünü okur; bu çıktıyı tüketen hiçbir şey yok.

Kullanım:
    python scripts/linkedin_login.py

LinkedIn'de bir Chromium penceresi açılır. Giriş yap, sonra terminalde ENTER'a bas.
Oturum credentials/linkedin_state.json'a kaydedilir (gitignore'da).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.applyjobs.config import CREDENTIALS_DIR, LINKEDIN_STATE_FILE  # noqa: E402


def main() -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.linkedin.com/login")
        print("\n>>> Log in to LinkedIn in the opened window.")
        input(">>> When you are fully logged in, press ENTER here to save the session... ")
        context.storage_state(path=str(LINKEDIN_STATE_FILE))
        print(f"Saved session to {LINKEDIN_STATE_FILE}")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
