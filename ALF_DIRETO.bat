@echo off
title ALF VISION (modo direto)

cd /d "%~dp0"

echo.
echo ==========================================
echo       ALF VISION - modo direto
echo ==========================================
echo.
echo   Roda o ALF pelo Python do projeto, sem
echo   passar pelo ALF.exe empacotado.
echo.
echo   Motivo: o Avast desta maquina intercepta
echo   o TLS e derruba a conexao do ALF.exe, que
echo   nao e assinado. O python.exe e assinado e
echo   passa sem problema.
echo.
echo        Alf esta iniciando...
echo.

if not exist "venv\Scripts\pythonw.exe" (
	echo ERRO: ambiente virtual nao encontrado em:
	echo %~dp0venv\Scripts\pythonw.exe
	pause
	exit /b 1
)

if not exist "main_basic.py" (
	echo ERRO: main_basic.py nao encontrado em:
	echo %~dp0
	pause
	exit /b 1
)

if not exist ".env" (
	echo ERRO: arquivo .env nao encontrado em:
	echo %~dp0.env
	pause
	exit /b 1
)

start "ALF" "%~dp0venv\Scripts\pythonw.exe" "%~dp0main_basic.py"

exit
