@echo off
echo ==============================================
echo       Iniciando EduPilot (Modo Local)
echo ==============================================

:: Activar entorno virtual
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo [ADVERTENCIA] No se encontro la carpeta venv local.
)

:: Aplicar migraciones pendientes si las hay
echo Verificando migraciones de base de datos...
python manage.py migrate --no-input

:: Iniciar el servidor de desarrollo
echo.
echo ==============================================
echo   EduPilot corriendo en: http://127.0.0.1:8000/
echo   Presiona CTRL+C para detener el servidor
echo ==============================================
python manage.py runserver 127.0.0.1:8000
pause
