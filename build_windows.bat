@echo off
REM Genera dist\MiMusica\MiMusica.exe (carpeta lista para comprimir y compartir)
cd /d "%~dp0"

if not exist "tools\ffmpeg.exe" goto falta
if not exist "tools\ffprobe.exe" goto falta

python -m pip install pyinstaller
if errorlevel 1 goto error

flet pack main.py -D -y -n MiMusica --distpath dist --product-name "Mi Musica" --file-description "Descargador y reproductor de musica"
if errorlevel 1 goto error

REM FFmpeg va junto al .exe, en dist\MiMusica\tools (la app lo busca ahi)
xcopy /E /I /Y "tools" "dist\MiMusica\tools" >nul
echo.
echo Listo: dist\MiMusica\MiMusica.exe
goto fin

:falta
echo Falta tools\ffmpeg.exe o tools\ffprobe.exe. Copialos y vuelve a ejecutar.
pause
exit /b 1

:error
echo Ocurrio un error durante la compilacion.
pause
exit /b 1

:fin
pause
