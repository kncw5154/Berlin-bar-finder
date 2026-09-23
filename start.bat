@echo off
REM Startdatei fuer Windows: per Doppelklick ausfuehren.
cd /d "%~dp0"
if not exist ".venv" (
  echo Erster Start: Richte Python-Umgebung ein ...
  python -m venv .venv || (echo Python nicht gefunden. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
echo Pruefe Pakete ...
python -m pip install -q -r requirements.txt
echo.
echo App startet im Browser. Zum Beenden dieses Fenster schliessen.
streamlit run app.py
pause
