@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === Pets Monitor: instalacao ===
where py >nul 2>nul || (echo Python nao encontrado. Instale o Python 3.11 ou 3.12 em python.org marcando "Add to PATH" e rode de novo. & pause & exit /b 1)
if not exist .venv (py -3 -m venv .venv || (echo Falha ao criar o ambiente. & pause & exit /b 1))
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Falha ao instalar as dependencias. & pause & exit /b 1)
if not exist .env copy .env.example .env >nul
if not exist config.yaml copy config.camera-properties.yaml config.yaml >nul
echo.
echo Pronto. Agora:
echo   1. Abra o arquivo .env e preencha SUPABASE_URL, SUPABASE_SERVICE_KEY e os dados do NVR.
echo   2. Copie o seu camera.properties (o mesmo do outro app) para esta pasta.
echo   3. Rode windows\testar.bat para conferir uma camera.
echo   4. Rode windows\iniciar.bat (ou windows\iniciar-com-o-windows.bat para subir sozinho).
pause
