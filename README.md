# Mi Música

Aplicación para **descargar audio de YouTube y YouTube Music**, importar enlaces de **Spotify** buscando versiones equivalentes en YouTube, organizar la música en una **biblioteca local** y reproducirla con un **reproductor integrado**. Un solo código en Python con interfaz [Flet](https://flet.dev), pensado para **Windows** (`.exe`) y **Android** (`.apk`).

> **Estado:** Windows funciona y se puede empaquetar como `.exe`. Android compila y reproduce, pero está en fase de pruebas (ver [Diferencias entre plataformas](#diferencias-entre-plataformas)).

<!-- Agrega aquí capturas de pantalla, por ejemplo:
![Escritorio](docs/escritorio.png) ![Móvil](docs/movil.png) -->

## Características

La versión **0.1.6** añade recuperación ante fallos: un escaneo fallido conserva la biblioteca y se puede reintentar; los escaneos tienen un límite de 30 segundos y descartan resultados de carpetas anteriores. El inicio del motor tiene un límite de 15 segundos para liberar la interfaz. Si una operación nativa sigue pendiente, se evita superponer otra y se detiene cualquier inicio tardío. Las portadas se cargan sin retener el cambio de canción. La reconexión recrea los trabajadores de biblioteca y portadas.

Las playlists se escriben de forma atómica con vaciado a disco y respaldo `.json.bak` del estado anterior guardado. Si el archivo principal está dañado, se intenta recuperar el respaldo. Los errores de escritura se muestran y los cambios permanecen en memoria para un guardado posterior. Las descargas simultáneas se agrupan en un único trabajo por descargador y un fallo inesperado del hilo se comunica a la interfaz.

La validación incluye **55 pruebas**, con fallos de disco, archivo JSON truncado, portadas lentas, reconexión, callbacks tardíos, motor que no responde, guardado concurrente y pulsaciones simultáneas. Son pruebas automatizadas con simulaciones; la validación en un teléfono Android sigue siendo necesaria. Los límites de tiempo no pueden terminar por la fuerza un hilo atascado dentro de una biblioteca nativa o del sistema operativo.

La versión **0.1.5** unifica el tema oscuro y verde en biblioteca, descargas, reproductores, menús, avisos y formularios. Incluye campos de texto consistentes, acciones destructivas en rojo y una marca visible de la canción activa. La búsqueda utiliza un índice preparado durante el escaneo; las portadas comparten una caché de hasta 24 MiB y 300 entradas, con dos trabajadores y cancelación de tareas pendientes al cambiar de lista. El progreso refresca solamente las vistas del reproductor.

- **Descargas:** videos, canciones, shorts, listas de reproducción y álbumes de YouTube y YouTube Music (`youtube.com`, `youtu.be`, `music.youtube.com`).
- **Enlaces de Spotify:** canciones y playlists públicas de menos de 100 canciones, con búsqueda por título, artista y duración, progreso por pista y cancelación. Usa el audio equivalente de YouTube y conserva el título y artista de Spotify.
- **Etiquetas y portada:** título, artista, álbum y carátula incrustados en el archivo.
- **Progreso en tiempo real,** botón de cancelar, y errores explicados en español (sin conexión, video privado, restricción de edad, etc.).
- **Biblioteca local:** escanea la carpeta de descargas al iniciar, con búsqueda por título, artista o álbum.
- **Playlists:** crear, renombrar, eliminar y añadir o quitar canciones. Se guardan en un archivo JSON.
- **Reproductor:** reproducir, pausar, detener, anterior, siguiente, barra de progreso con salto, volumen y paso automático a la siguiente canción.
- **Modo aleatorio** sin repeticiones hasta agotar la lista.
- **Portadas** en el reproductor y en la lista de canciones.
- **Eliminar canciones:** desde el menú ⋮ (o con pulsación larga), con confirmación. Borra el archivo y la quita de las playlists y de la cola; si estaba sonando, pasa a la siguiente.
- **Reproducción en segundo plano (Android):** la música sigue sonando con la app en segundo plano o con la pantalla bloqueada, con una notificación multimedia que muestra la portada, el título, el artista y el tiempo, con botones de anterior, pausar/reanudar y siguiente (también en la pantalla de bloqueo).
- **Controles del sistema en Windows (opcional):** la canción que suena aparece en el panel de medios de Windows (al cambiar el volumen y en la pantalla de bloqueo), con pausar, siguiente y anterior, y responde a las teclas multimedia del teclado. Se activa instalando `requirements-multimedia.txt`.
- **Interfaz oscura y responsiva, estilo Spotify / YouTube Music:**
  - **Escritorio:** dos paneles y una barra inferior de tres zonas (pista, controles con progreso, volumen).
  - **Móvil:** un panel a la vez con barra de navegación, un mini-reproductor compacto y, al tocarlo, una pantalla de reproducción completa con carátula grande.
  - **Teclado en pantalla:** al abrirlo se ocultan el encabezado, el mini-reproductor y la navegación para que el campo de texto y la lista tengan todo el espacio.
  - **Listas largas:** las filas se crean por tandas al hacer scroll, así que la biblioteca abre rápido aunque tenga cientos de canciones.
- **Atajos en escritorio:** `Ctrl+Espacio` (reproducir/pausar), `Ctrl+→` / `Ctrl+←` (siguiente/anterior) y `Ctrl+F` (buscar).

## Usar enlaces de Spotify

En **Descargar**, pega el enlace completo de una canción o playlist de `open.spotify.com` y pulsa **Descargar audio**. También se aceptan enlaces regionales (`/intl-es/`) y URI `spotify:track:…` / `spotify:playlist:…`. No se necesita iniciar sesión ni configurar claves.

La app consulta la página pública de Spotify y busca hasta cinco candidatos en YouTube. Compara título, artista y duración, favorece el canal del artista y evita versiones como karaoke, covers o remixes cuando no se pidieron. Si no encuentra una coincidencia compatible, avisa y continúa con las demás pistas. La versión de audio puede diferir de la de Spotify. Los archivos se añaden a la biblioteca; descargar una playlist no crea automáticamente una playlist local.

Se admiten playlists públicas con **hasta 99 canciones**. La vista pública puede recortar las listas largas; si se detecta ese límite, la app pide dividir la playlist para evitar presentar una importación parcial como completa. No se admiten playlists privadas, álbumes, podcasts ni enlaces cortos `spotify.link`. Para un enlace corto, ábrelo en el navegador y copia el enlace completo `open.spotify.com`.

Spotify aporta los títulos y artistas; el audio y la portada proceden de YouTube. No se exporta audio del servicio Spotify ni se usan sus avances de 30 segundos. Los cambios en las páginas públicas de Spotify o en YouTube pueden requerir actualizar la integración.

## Requisitos

- Python 3.10 o superior (desarrollado con 3.13).
- **FFmpeg y FFprobe** (solo Windows): ambos `.exe` son necesarios para convertir a MP3.
- Opcional: `deno.exe`, que yt-dlp usa para resolver los retos de JavaScript de YouTube.

## Instalación y ejecución (Windows)

```bash
git clone https://github.com/Akane36v/Reproductor-de-musica.git
cd Reproductor-de-musica

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copia `ffmpeg.exe` y `ffprobe.exe` a la carpeta `tools/` (la app también los busca junto al proyecto y en el PATH). Luego:

```bash
python main.py          # o: flet run main.py
```

Las descargas van a tu carpeta **Descargas** de Windows. Las playlists se guardan en `%APPDATA%\MiMusica\playlists.json`.

## Generar el ejecutable de Windows

Haz doble clic en `build_windows.bat` (o ejecútalo desde la terminal). Usa `flet pack` en modo carpeta y deja el resultado en:

```
dist\MiMusica\MiMusica.exe
```

Comprime la carpeta `dist\MiMusica` completa para compartirla: la subcarpeta `tools/` con FFmpeg debe viajar junto al `.exe`.

## Generar el APK de Android

Requisitos: Windows con el **Modo desarrollador** activado (`start ms-settings:developers`) y varios GB libres. La primera vez, Flet descarga Flutter, el JDK y el Android SDK.

Haz doble clic en `build_android.bat`. El APK queda en `dist\`. Para instalarlo, pásalo al teléfono y permite la instalación de apps desconocidas.

El script compila desde una copia temporal sin `tools/`, cierra procesos de Gradle antiguos y reintenta una vez si Windows bloquea un archivo.

## Diferencias entre plataformas

| | Windows | Android |
|---|---|---|
| Formato descargado | **MP3** 192 kbps (FFmpeg) | **M4A** (AAC original, sin recodificar) |
| Etiquetas y portada | FFmpeg | mutagen |
| Carpeta de música | Descargas | Almacenamiento privado de la app |
| Elegir carpeta | Sí | No |
| Motor de audio | pygame | Control `Audio` de Flet |

Notas de Android:

- Android no incluye FFmpeg, por eso se descarga el audio AAC nativo en vez de convertir a MP3.
- La música se guarda en el almacenamiento privado de la app: no aparece en el explorador de archivos y se borra al desinstalar. Exportarla a la carpeta pública es un trabajo pendiente.
- Las descargas se pausan si bloqueas la pantalla o cambias de app.
- **Segundo plano y notificación:** funcionan con una extensión propia (`extensions/flet-media-session`, servicio en primer plano con MediaSession). En Android 13 o superior la app pide permiso de notificaciones la primera vez que suena una canción; sin él, el audio sigue en segundo plano pero la notificación no se ve. Si cierras la app desde "recientes", la música se detiene. Algunos fabricantes (Xiaomi, Huawei, Samsung...) cierran apps en segundo plano: si pasa, desactiva la optimización de batería para Mi Música.
- YouTube exige cada vez más un runtime de JavaScript para extraer formatos, y Android no tiene uno disponible. Si las descargas fallan en el teléfono, es la primera causa a revisar.

## Arquitectura

El núcleo no depende de la interfaz ni del sistema operativo. Cada plataforma implementa los mismos contratos y `bootstrap.py` elige cuál usar.

```
main.py                         # punto de entrada
build_windows.bat               # genera el .exe
build_android.bat               # genera el .apk
pyproject.toml                  # configuración de "flet build apk"
requirements.txt                # dependencias de escritorio
extensions/
├── flet_media_session-0.1.0-py3-none-any.whl   # extensión de Android ya empaquetada
└── flet-media-session/                          # su código fuente (Python, Dart y Java)
tools/                          # FFmpeg portátil (no se sube a git)
mimusica/
├── bootstrap.py                # elige los adaptadores según la plataforma
├── core/                       # lógica pura (sin Flet, sin pygame)
│   ├── models.py               # Cancion, Playlist
│   ├── ports.py                # contratos: Descargador, Reproductor, Plataforma
│   ├── urls.py                 # validación de enlaces
│   ├── errors.py               # errores de yt-dlp traducidos
│   ├── formatting.py
│   └── services/
│       ├── library.py          # escaneo y lectura de etiquetas
│       ├── queue.py            # cola de reproducción y modo aleatorio
│       ├── playlists.py        # playlists en JSON
│       └── covers.py           # portadas incrustadas
├── adapters/
│   ├── windows/                # yt-dlp + FFmpeg, pygame, carpeta Descargas, controles multimedia (SMTC)
│   └── android/                # yt-dlp sin FFmpeg, flet-audio, notificación multimedia, almacenamiento de la app
└── ui/
    ├── app.py                  # pantallas, lógica de la interfaz y diseño responsivo
    ├── player_views.py         # barra de escritorio, mini-reproductor y pantalla completa
    └── theme.py
```

Regla de dependencias: `ui` → `core` ← `adapters`. Para añadir otra plataforma basta con crear su carpeta en `adapters/` y registrarla en `bootstrap.py`.

## Solución de problemas

- **"Falta una herramienta" / FFmpeg no encontrado:** coloca `ffmpeg.exe` **y** `ffprobe.exe` en `tools/`.
- **Una descarga falla de repente:** YouTube cambia con frecuencia. Actualiza con `pip install -U yt-dlp`. En el `.exe` hay que volver a generarlo para actualizar yt-dlp.
- **Pylance marca `mimusica` como no resuelto:** abre en VS Code la carpeta que contiene `main.py`.
- **No aparece la canción en el panel de medios de Windows:** instala `pip install -r requirements-multimedia.txt`. Para ver el motivo exacto: `python -c "from mimusica.adapters.windows.media_controls import ControlesMultimediaWindows as C; print(C(print).error)"`.
- **El antivirus o SmartScreen avisa del `.exe`:** es habitual en ejecutables de PyInstaller sin firma digital.
- **El build de Android falla mencionando `flet_media_session`, Gradle o Dart:** guarda el texto del error (desde `FAILURE` o el primer `Error`). La extensión de la notificación es código propio y es lo más probable que necesite ajustes.
- **El audio se detiene en segundo plano o falla de forma rara:** toca el icono de bicho (arriba a la derecha) para abrir **Diagnóstico**, pulsa «Copiar todo» y pega el registro al reportar el problema. Incluye eventos del motor de audio, del ciclo de vida de la app y de la notificación.
- **No aparece la notificación en Android:** acepta el permiso de notificaciones (Ajustes → Apps → Mi Música → Notificaciones) y revisa que la optimización de batería no la esté cerrando.
- **El build de Android falla con "being used by another process":** cierra Android Studio y agrega una exclusión del antivirus para `%TEMP%\mimusica_android_build`.

## Pendiente

- Dividir `ui/app.py` en componentes (panel de descargas, biblioteca y reproductor).
- Pruebas automáticas del núcleo.
- Mecanismo de actualización de yt-dlp dentro del ejecutable.
- Exportar música a la carpeta pública en Android y descargas en segundo plano.
- Instalador para Windows y firma digital del ejecutable.

## Aviso legal

Este proyecto es **independiente** y no está afiliado a YouTube ni a Google. Úsalo únicamente con contenido que tengas derecho a descargar, y respeta los términos de servicio de YouTube y las leyes de derechos de autor de tu país. El autor no se hace responsable del uso que se le dé.

## Licencia

Por definir. Agrega un archivo `LICENSE` antes de publicar (por ejemplo MIT).

## Créditos

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [FFmpeg](https://ffmpeg.org) · [Flet](https://flet.dev) · [mutagen](https://github.com/quodlibet/mutagen) · [pygame](https://www.pygame.org)

## Corrección de audio en Android · 0.1.1

Se consulta la posición real del motor cada segundo para vigilar el audio con la pantalla bloqueada. Las cargas y la recuperación se procesan en orden, con prioridad para la última selección. El registro de Diagnóstico identifica el reproductor v2 y añade muestras de posición cada quince segundos.

Las pruebas simuladas se ejecutan con `python -m unittest discover -s tests -v`. Sigue pendiente confirmar en un teléfono la reproducción prolongada y los cambios rápidos de canción.
