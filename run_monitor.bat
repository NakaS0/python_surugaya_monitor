@echo off
cd /d %~dp0
.\venv\Scripts\python.exe app.py watch --ui-host 127.0.0.1 --ui-port 8080
