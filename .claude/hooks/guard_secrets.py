"""PreToolUse hook'u: gizli dosyalara ve kullanıcının LinkedIn oturumuna erişimi engeller.

Claude Code her araç çağrısından önce bunu çalıştırır ve çağrının JSON'unu stdin'den verir.
Çıkış kodu 2 çağrıyı engeller; stderr'deki gerekçe agent'a gösterilir.

Korunanlar:
  * credentials/  — Google servis hesabı, OAuth token'ı, Huntr profili
  * .env (ve .env.bak*) — API anahtarı ve sheet kimliği (.env.example serbest)
  * linkedin_state.json — kullanıcının LinkedIn oturum çerezi. Bu çerez bir kez otomasyona
    bağlandı ve LinkedIn hesabı "oturum çalınmış" sayıp haftalarca bütün oturumları kapattı.
    Hiçbir agent bu dosyaya dokunmamalı (bkz. CLAUDE.md, "Kullanıcının LinkedIn oturumunu
    otomatikleştirme").
"""
from __future__ import annotations

import json
import re
import sys

_PATTERNS = [
    (re.compile(r"(?:^|[/\s\"'=])credentials/"), "credentials/ klasörü gizli anahtarlar içerir"),
    (re.compile(r"(?<![\w.])\.env(?:\.bak\S*)?(?![\w.-])"), ".env gizli anahtarlar içerir"),
    (re.compile(r"linkedin_state\.json"),
     "linkedin_state.json kullanıcının LinkedIn oturumudur; otomasyona asla bağlanmaz"),
]


# Sadece "neye erişiliyor?" sorusunu cevaplayan alanlar taranır. Write/Edit'in içerik alanları
# (content, new_string…) taranmaz: .env'den ya da credentials/'tan BAHSEDEN bir belge yazmak
# o dosyalara erişmek değildir.
_PATH_FIELDS = ("file_path", "path", "notebook_path", "pattern", "command")


# Bash komutunda tırnak içindeki metin (commit mesajı, echo metni…) taranmaz: bir commit
# mesajında ".env" geçmesi dosyaya erişmek değildir. Bedeli küçük bir boşluk: `cat ".env"`
# gibi tırnaklı bir yol buradan geçer; Read aracı için settings.json'daki deny kuralları
# ayrıca korur, başsız CV oturumlarında ise Bash tamamen kapalıdır (agent_runner).
_QUOTED = re.compile(r"\"(?:\\.|[^\"\\])*\"|'[^']*'")


def _strings(tool_input: dict):
    for field in _PATH_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str):
            yield _QUOTED.sub(" ", value) if field == "command" else value


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # bozuk girdi: engelleme kararı veremeyiz, aracı durdurma
    tool_input = event.get("tool_input") or {}
    for text in _strings(tool_input):
        for pattern, reason in _PATTERNS:
            if pattern.search(text):
                print(
                    f"Engellendi ({event.get('tool_name', '?')}): {reason}. "
                    "Bu dosyaya agent'lar erişmez; gerekiyorsa kullanıcıdan iste.",
                    file=sys.stderr,
                )
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
