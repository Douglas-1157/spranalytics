@echo off
chcp 65001 >nul
title SprAnalytics
cd /d "%~dp0"
echo Instalando/conferindo componentes (so demora na primeira vez)...
py -m pip install -r requirements.txt >nul 2>&1 || python -m pip install -r requirements.txt
echo.
echo Abrindo o SprAnalytics em http://localhost:5000
start "" http://localhost:5000
py app.py || python app.py
pause
