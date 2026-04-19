@echo off
chcp 65001 >nul
rem Change to project root (parent of this folder)
cd /d "%~dp0.."

rem Show URL
echo Starting dashboard server at http://localhost:8000/dashboard.html

rem Open Chrome if installed, otherwise fallback to default browser
set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME_PATH%" (
    start "" "%CHROME_PATH%" "http://localhost:8000/dashboard.html"
) else (
    start "" "http://localhost:8000/dashboard.html"
)

rem Launch simple HTTP server (Python 3)
python dashboard_server.py
