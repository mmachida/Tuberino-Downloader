@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERRO] Ambiente Python nao encontrado em .venv.
    echo Execute o setup descrito no README.md antes de iniciar o aplicativo.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" -m app
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERRO] O aplicativo terminou com codigo %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
