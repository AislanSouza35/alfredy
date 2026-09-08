@echo off
title ALF VISION

cd /d "%~dp0"

echo.
echo ==========================================
echo          ALF VISION
echo ==========================================
echo.
echo        Alf esta iniciando...
echo        Aguarde alguns segundos.
echo.

if not exist "venv\Scripts\python.exe" (
	echo ERRO: ambiente virtual nao encontrado em:
	echo %~dp0venv\Scripts\python.exe
	pause
	exit /b 1
)

if not exist "dist\ALF\ALF.exe" (
	echo ERRO: executavel nao encontrado em:
	echo %~dp0dist\ALF\ALF.exe
	pause
	exit /b 1
)

if not exist "dist\ALF\.env" (
	echo ERRO: arquivo .env nao encontrado em:
	echo %~dp0dist\ALF\.env
	pause
	exit /b 1
)

start "ALF" /wait "%~dp0dist\ALF\ALF.exe"

if errorlevel 1 (
	echo.
	echo O programa foi encerrado com erro.
	pause
)

exit