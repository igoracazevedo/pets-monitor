@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
:laco
echo [%date% %time%] iniciando a varredura...
python -m pets_agent varrer
echo [%date% %time%] o programa parou; reiniciando em 10 s (Ctrl+C para sair)
timeout /t 10 /nobreak >nul
goto laco
