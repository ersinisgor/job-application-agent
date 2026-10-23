#!/usr/bin/env bash
# YALNIZCA LinkedIn İlan Özeti API'sini (tarayıcı eklentisinin backend'i) başlatır, CV poller'ı
# olmadan. LinkedIn'de gezinirken bunu kullan: poller (CV agent'ı üzerinden) LinkedIn ilan
# sayfalarını başsız bir tarayıcıyla okur ve kendi IP'nden gelen bu otomasyon trafiği hesabın
# işaretli kalmasına (sürekli oturum kapanmasına) yol açıyordu.
#
# Kullanım:
#   ./scripts/start_api.sh
set -euo pipefail

cd "$(dirname "$0")/.."
PY=./.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "Virtualenv not found at .venv. Create it and install deps:"
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Starting LinkedIn Job Summary API only (no CV poller). Press Ctrl+C to stop."
exec "$PY" scripts/run_summary_api.py
