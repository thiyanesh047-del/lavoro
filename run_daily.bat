@echo off
REM Daily run for Windows Task Scheduler. The AI steps use the `claude` command (Claude Code) signed in
REM with your Claude plan, so run the task as your own Windows user. No API key is needed.
REM Extra arguments are passed on, e.g.:  run_daily.bat --region europe
cd /d "%~dp0"
if not exist output mkdir output
echo. >> "output\run.log"
echo ===== %DATE% %TIME% ===== >> "output\run.log"
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python -m lavoro run %* >> "output\run.log" 2>&1
) else (
  py -m lavoro run %* >> "output\run.log" 2>&1
)
