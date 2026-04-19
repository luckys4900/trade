@echo off
chcp 65001 > nul
cd /d "%~dp0"
python one_click_deploy.py
pause
