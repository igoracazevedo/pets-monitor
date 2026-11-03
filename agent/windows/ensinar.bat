@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
python -m pets_agent ensinar --pasta fotos
echo.
pause
