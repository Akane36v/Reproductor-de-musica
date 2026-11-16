@echo off
REM Genera el APK de Android. La primera vez descarga Flutter, JDK y Android SDK (tarda y ocupa varios GB).
cd /d "%~dp0"

set TMPB=%TEMP%\mimusica_android_build

REM Cierra procesos de Gradle de compilaciones anteriores (si no, Windows puede bloquear archivos)
call :parar_gradle

if exist "%TMPB%" rmdir /s /q "%TMPB%"
mkdir "%TMPB%"

REM Copia limpia del proyecto: sin tools\ (FFmpeg de Windows pesa mucho y no se usa en Android)
robocopy "%~dp0." "%TMPB%" /E /XD tools dist build .venv .git __pycache__ .flet flet-media-session /XF *.bat >nul

cd /d "%TMPB%"
flet build apk -v
if not errorlevel 1 goto listo

echo.
echo La compilacion fallo. Reintentando una vez (a veces Windows bloquea un archivo temporal)...
call :parar_gradle
timeout /t 5 /nobreak >nul
flet build apk -v
if errorlevel 1 goto error

:listo
if not exist "%~dp0dist" mkdir "%~dp0dist"
copy /Y "build\apk\*.apk" "%~dp0dist\" >nul
echo.
echo Listo: busca el .apk en la carpeta dist
goto fin

:error
echo.
echo Ocurrio un error durante la compilacion. Guarda el texto de arriba (desde "FAILURE" o el
echo primer "Error") para revisarlo. Si dice "being used by another process", agrega una
echo exclusion en Seguridad de Windows para: %TMPB%
pause
exit /b 1

:fin
pause
exit /b 0

:parar_gradle
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'java.exe' -and $_.CommandLine -like '*GradleDaemon*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
exit /b 0
