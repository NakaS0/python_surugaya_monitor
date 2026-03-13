@echo off
REM Django サーバーを起動して、ブラウザでダッシュボードを開く
REM .env がある場合は本番用を初期表示にする
if /I not "%~1"=="hidden" (
  powershell -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath '%ComSpec%' -ArgumentList '/c','\"%~f0\" hidden'"
  exit /b
)

cd /d %~dp0
powershell -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath 'venv\\Scripts\\python.exe' -ArgumentList 'manage.py','runserver','127.0.0.1:8080' -WorkingDirectory '%~dp0'"
timeout /t 3 /nobreak >nul
if exist ".env" (
  start "" "http://127.0.0.1:8080/?active_set=1"
) else (
  start "" "http://127.0.0.1:8080/"
)
