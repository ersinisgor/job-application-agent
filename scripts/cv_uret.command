#!/usr/bin/env bash
# Double-click me in Finder to generate CVs for every row you marked.
#
# The sheet has no real button (it is an .xlsx in Drive: openpyxl drops macros on every
# write, Google Sheets runs no Apps Script on Office files, and Apps Script could not reach
# this machine anyway). This is the button: mark the rows you are about to apply to with
# Başvuru (B) = "Üretilecek", save, then double-click this file. One pass, then it stops.
#
# Also runnable from a terminal: ./scripts/cv_uret.command
set -euo pipefail

cd "$(dirname "$0")/.."
PY=./.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "Virtualenv not found at .venv. Create it and install deps:"
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  # `|| true`: with no terminal attached (piped/cron) read fails, and set -e would abort
# here — turning a successful run into a non-zero exit.
read -n 1 -s -r -p "Kapatmak için bir tuşa bas..." || true
  exit 1
fi

# Claude Code exports its own CLAUDE_EFFORT, and load_dotenv() does not override an
# existing env var — so without this a run started from a Claude Code shell would silently
# use that effort instead of .env's. Harmless when double-clicked from Finder.
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
# `|| true`: with no terminal attached (piped/cron) read fails, and set -e would abort
# here — turning a successful run into a non-zero exit.
read -n 1 -s -r -p "Kapatmak için bir tuşa bas..." || true
echo
exit "$STATUS"
