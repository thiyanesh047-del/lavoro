@echo off
REM Double-click to open Lavoro. It starts the site in the background (no window stays open) and opens it in
REM your browser. If the site is already running, it just opens the browser.
REM To close the site later:  python -m lavoro stop
REM To start it every time you log in: press Win+R, type  shell:startup , and put a shortcut to this file there.
cd /d "%~dp0"
if not exist output mkdir output
where pythonw >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" pythonw -m lavoro serve --open
) else (
  start "Lavoro" /min python -m lavoro serve --open
)
