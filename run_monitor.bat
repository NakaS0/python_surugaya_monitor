@echo off
REM Django 開発サーバーを起動し、少し待ってからブラウザを開くバッチです。
REM ダブルクリックで画面確認したいときの入口として使います。
cd /d %~dp0
start "Suruga-ya Check Server" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe manage.py runserver 127.0.0.1:8080"
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8080/
