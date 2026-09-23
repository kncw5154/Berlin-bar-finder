#!/bin/bash
# Startdatei für macOS: per Doppelklick ausführen.
# Richtet beim ersten Start alles ein und startet dann die App im Browser.

cd "$(dirname "$0")" || exit 1   # in den Ordner wechseln, in dem diese Datei liegt

if [ ! -d ".venv" ]; then
  echo "Erster Start: Richte Python-Umgebung ein ..."
  python3 -m venv .venv || { echo "Python 3 nicht gefunden."; read -r -p "Enter zum Schliessen"; exit 1; }
fi

source .venv/bin/activate
echo "Pruefe Pakete ..."
python3 -m pip install -q -r requirements.txt

echo ""
echo "App startet im Browser. Zum Beenden dieses Fenster schliessen (oder Ctrl + C)."
streamlit run app.py
