@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
if "%~1"=="" (set /p IPCAM=IP da camera: ) else (set IPCAM=%~1)
if "%~2"=="" (set /p USR=Usuario da camera (Enter se nao tem): ) else (set USR=%~2)
if "%~3"=="" (set /p PWD=Senha da camera (Enter se nao tem): ) else (set PWD=%~3)
python -m pets_agent sondar "%IPCAM%" "%USR%" "%PWD%"
pause
