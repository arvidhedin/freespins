#!/bin/zsh
# Startar bonussökaren lokalt på http://localhost:8503
# Dubbelklicka i Finder, eller kör ./start.command i terminalen. Stäng med Ctrl+C.

cd "$(dirname "$0")"
URL="http://localhost:8503"
PY="/opt/anaconda3/bin/python3"
[[ -x "$PY" ]] || PY="python3"

# Kör den redan? Öppna bara webbläsaren.
if curl -s --max-time 1 "$URL/_stcore/health" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

# Första gången: hämta licensregistren (sökningen av kasinona startar du i appen).
if [[ ! -f data/kasinon.json ]]; then
  echo "Hämtar licensregistren (första gången tar det någon minut) …"
  "$PY" verktyg/skanna.py --bara-register
fi

( for i in {1..30}; do
    sleep 0.5
    if curl -s --max-time 1 "$URL/_stcore/health" >/dev/null 2>&1; then open "$URL"; break; fi
  done ) &

exec "$PY" -m streamlit run app.py
