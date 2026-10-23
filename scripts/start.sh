#!/usr/bin/env bash
# Bir iş arama oturumu için her şeyi TEK komutla başlatır:
#   - LinkedIn İlan Özeti API'si (tarayıcı eklentisinin backend'i)
#   - sürekli çalışan CV poller'ı (src/applyjobs/main.py) — B="Üretilecek" satır görünce
#     CV agent'ını (claude -p "/cv-uret") başlatır
# Ctrl+C ikisini de durdurur.
#
# Kullanım:
#   ./scripts/start.sh
set -euo pipefail

cd "$(dirname "$0")/.."
PY=./.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "Virtualenv not found at .venv. Create it and install deps:"
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Starting LinkedIn Job Summary API + CV poller. Press Ctrl+C to stop both."

"$PY" scripts/run_summary_api.py &
API_PID=$!

"$PY" -m src.applyjobs.main &
POLLER_PID=$!

# Çıkışta (Ctrl+C / TERM) iki alt süreci de durdur.
cleanup() {
  kill "$API_PID" "$POLLER_PID" 2>/dev/null || true
  wait "$API_PID" "$POLLER_PID" 2>/dev/null || true
}
trap cleanup INT TERM

# Süreçlerden biri bitene kadar bekle, sonra diğerini durdur (bash 3.2 uyumlu).
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$POLLER_PID" 2>/dev/null; do
  sleep 1
done
cleanup
