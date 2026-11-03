@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set RAIZ=%CD%
echo Registrando o Pets Monitor para iniciar com o Windows...
schtasks /Create /TN "PetsMonitor" /TR "\"%RAIZ%\windows\iniciar.bat\"" /SC ONLOGON /RL LIMITED /F
if errorlevel 1 (echo Nao consegui criar a tarefa. Execute este arquivo como administrador. & pause & exit /b 1)
echo Evitando que o PC entre em suspensao enquanto na tomada...
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
echo Pronto. Na proxima vez que voce entrar no Windows, a varredura comeca sozinha.
echo Para remover: schtasks /Delete /TN "PetsMonitor" /F
pause
