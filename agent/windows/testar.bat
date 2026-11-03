@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
if "%~1"=="" (set /p CAM=Nome da camera conforme o config.yaml: ) else (set CAM=%~1)
python -m pets_agent testar "%CAM%"
pause
