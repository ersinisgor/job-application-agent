#!/usr/bin/env bash
# İşaretlediğin her satır için CV üretmek üzere Finder'da bana çift tıkla.
#
# Sheet'te gerçek bir buton olamaz (Drive'daki bir .xlsx: openpyxl her yazımda makroları
# düşürür, Google Sheets Office dosyalarında Apps Script çalıştırmaz ve Apps Script zaten bu
# makineye ulaşamaz). Buton bu: başvurmak üzere olduğun satırları Başvuru (B) = "Üretilecek"
# yap, kaydet, sonra bu dosyaya çift tıkla. CV'yi Claude Code agent'ı üretir (/cv-uret);
# tek geçiş yapar ve durur.
#
# Terminalden de çalışır: ./scripts/cv_uret.command
set -euo pipefail

cd "$(dirname "$0")/.."
PY=./.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "Virtualenv not found at .venv. Create it and install deps:"
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  # `|| true`: terminal bağlı değilse (pipe/cron) read başarısız olur ve set -e burada
# durdururdu — başarılı bir çalışmayı sıfır olmayan bir çıkışa çevirirdi.
read -n 1 -s -r -p "Kapatmak için bir tuşa bas..." || true
  exit 1
fi

# Eskiden CLAUDE_EFFORT, Claude Code'un kendi değişkeniyle çakışıyordu. Agent sistemi artık
# CV_EFFORT kullanıyor (agent_runner child ortamdan CLAUDE_EFFORT'u zaten siler); bu satır
# zararsız bir güvenlik önlemi olarak duruyor.
unset CLAUDE_EFFORT

echo "Başvuru (B) = 'Üretilecek' olan satırlar için CV üretiliyor…"
echo

set +e
"$PY" scripts/run_once.py "$@"
STATUS=$?
set -e

echo
if [ "$STATUS" -ne 0 ]; then
  echo "Hata ile bitti (çıkış kodu $STATUS). Ayrıntı: state/agent.log, state/failures.log"
fi
# `|| true`: terminal bağlı değilse (pipe/cron) read başarısız olur ve set -e burada
# durdururdu — başarılı bir çalışmayı sıfır olmayan bir çıkışa çevirirdi.
read -n 1 -s -r -p "Kapatmak için bir tuşa bas..." || true
echo
exit "$STATUS"
