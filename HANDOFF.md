## Actualización del 15 de noviembre de 2026 · versión 0.1.4

Se añadieron enlaces de canciones y playlists públicas de Spotify al panel Descargar, en Windows y Android. `adapters/spotify.py` consulta los metadatos públicos del reproductor insertado de Spotify y busca coincidencias en YouTube usando yt-dlp. No requiere cuenta ni claves. Los nombres y etiquetas conservan título y artista de Spotify; el archivo y la portada proceden de YouTube. Se compara título, artista y duración y se evitan versiones no solicitadas. No se extrae audio de Spotify.

Las playlists se procesan secuencialmente con progreso por pista, cancelación y continuación ante fallos individuales. El alcance es canciones y playlists públicas de hasta 99 canciones. Se rechazan listas posiblemente truncadas, privadas y otros tipos de recurso, con mensajes claros. Los enlaces cortos deben abrirse y copiarse como `open.spotify.com`. No se crea una playlist local automáticamente. El proveedor público puede cambiar y requerir mantenimiento.

Validación: 29 pruebas automáticas aprobadas, incluidas las 9 regresiones de audio previas. Se consultó en vivo el enlace aportado por el usuario (Papercut, Linkin Park) y se descargó un M4A de prueba con el adaptador Android ejecutado en Windows; se verificaron duración, título y artista con mutagen. También se leyó una playlist pública de ejemplo con 5 canciones. La selección, fallos y cancelación de lotes se comprobaron con simulaciones. No se compiló ni ejecutó en un teléfono Android por indicación del usuario. La lógica de reproducción se conserva.

## Actualización del 15 de noviembre de 2026 · versión 0.1.3

Interfaz refinada con el mismo estilo oscuro y verde. Las playlists usan filtros compactos junto al buscador y la creación tiene un botón siempre visible. La lista dispone de más espacio y los estados de biblioteca vacía, playlist vacía y búsqueda sin resultados explican qué hacer. El minirreproductor mantiene juntos los controles de reproducción y avance, con etiquetas de pausa/reproducción según el estado.

La búsqueda agrupa pulsaciones durante 180 ms e invalida solicitudes pendientes al borrar, enviar o cambiar de playlist. Las filas muestran inmediatamente las portadas disponibles; las cargas por lotes ya no reconstruyen las playlists. La caché descarta una portada antigua al llegar al límite en lugar de vaciarse completa. El escaneo evita solicitudes simultáneas.

Se comprobó la construcción y visualización en Windows en tamaños móvil y escritorio. La comprobación con 120 canciones de ejemplo cubrió paginación inicial, escritura rápida, resultados vacíos, borrado inmediato, selección de playlists y reutilización de portadas. No se compiló Android por indicación del usuario. El núcleo, los adaptadores y la lógica de reproducción conservan la versión 0.1.2. La revisión en el teléfono corresponde al usuario después de compilar.

## Actualización del 13 de noviembre de 2026 · versión 0.1.2

El usuario confirmó que la reproducción funciona correctamente con la versión 0.1.1.

La versión 0.1.2 adapta la interfaz a la referencia visual aportada. Usa cabecera cálida, fondo oscuro, filas compactas, portadas cuadradas, botón circular verde, tarjetas para las playlists existentes y minirreproductor gris. Las tarjetas utilizan portadas ya disponibles en la biblioteca. Conserva las acciones existentes de biblioteca, búsqueda, playlists, descargas y reproducción. El núcleo y los adaptadores coinciden con 0.1.1.

Se revisó la interfaz renderizada en Windows en tamaños móvil y escritorio, con canciones de ejemplo, el reproductor ampliado y la selección de playlists. La apariencia en un teléfono Android queda pendiente de confirmación.

## Actualización del 10 de noviembre de 2026 · versión 0.1.1

Esta sección sustituye el estado del vigilante descrito más abajo.

Los registros del teléfono muestran reanudaciones cada cuatro segundos en segundo plano y cargas superpuestas tras cambios rápidos. Los eventos de posición de audioplayers dependen de fotogramas. Un estado playing por sí solo no confirma avance audible.

El adaptador consulta get_current_position una vez por segundo, comprueba avance real y limita la recuperación a reanudar una vez y recrear una vez. Registra la posición cada quince segundos. Serializa cargas, comandos y recuperación con un bloqueo asíncrono. Cada pista utiliza un control Audio distinto, con autoplay desactivado durante la preparación y liberación explícita del anterior. Las solicitudes obsoletas y sus eventos se descartan. La interfaz agrupa selecciones rápidas y serializa el inicio de reproducción.

Validación automatizada en tests/test_android_player.py. Ejecutar python -m unittest discover -s tests -v. Estas simulaciones comprueban orden de operaciones y estado, sin reproducir sonido ni simular el sistema Android. La confirmación de reproducción prolongada con pantalla bloqueada y ausencia de cierres queda pendiente en el teléfono.

# Traspaso del proyecto «Mi Música»

Documento para que otro asistente (ChatGPT u otro) continúe el proyecto exactamente donde se dejó.
Léelo completo antes de tocar código. El código fuente está en el zip `mimusica.zip` que acompaña
a este archivo; este documento explica el contexto, las decisiones, lo que está verificado y lo que no.

---

## 0. Cómo trabajar con el usuario (léelo primero)

- **Idioma:** español, siempre. La interfaz, los comentarios del código y los mensajes al usuario están en español.
- **El usuario** es estudiante universitario de ingeniería en sistemas. Prueba todo en su propio equipo
  (Windows 11) y en su teléfono Android. Te pasará errores, capturas o logs: pídelos siempre que algo falle.
- **Honestidad ante todo:** distingue siempre entre «probado de verdad» y «escrito pero no compilado/probado».
  Gran parte del código Android (Java, Dart, Gradle) no se puede compilar ni ejecutar en el entorno donde
  se desarrolló; solo lo puede validar el usuario. No afirmes que algo funciona si no se ha probado en su equipo.
- **No supongas, verifica:** varios diagnósticos previos fueron incorrectos por suposiciones. Cuando una API de
  Flet sea dudosa, lee su código fuente (ver sección 8) en vez de recordar de memoria.
- **Respuestas:** directas, con pasos concretos. Evita relleno. Cuando entregues cambios, entrega el proyecto completo
  actualizado (zip) y di qué probaste y qué no.
- **Un aviso legal:** el proyecto descarga audio de YouTube con yt-dlp. Es de uso personal; el README ya incluye un aviso.
  YouTube/Google podrían retirar repositorios públicos similares. No es un tema técnico, pero conviene recordarlo si se publica.

---

## 1. Qué es el proyecto

Aplicación **multiplataforma en Python con Flet 1.x** para:

1. **Descargar audio** de YouTube y YouTube Music (videos, canciones, shorts, listas, álbumes) con **yt-dlp**.
2. **Biblioteca local** con búsqueda, portadas, **playlists** persistentes, **modo aleatorio** y **borrar canciones**.
3. **Reproductor integrado**, con interfaz oscura estilo Spotify / YouTube Music, responsiva:
   - Escritorio: dos paneles + barra inferior de tres zonas.
   - Móvil: un panel a la vez + mini-reproductor + pantalla completa «Reproduciendo» + barra de navegación.
4. **Android:** reproducción en segundo plano y **notificación multimedia** con portada, tiempo y botones, mediante una
   **extensión propia de Flet** (`flet-media-session`).
5. **Windows:** controles multimedia del sistema (SMTC) opcionales mediante `winrt`.

Orden de plataformas acordado: **Windows primero (hecho), luego Android (en curso)**. **iOS está en pausa** hasta nuevo aviso del usuario.

---

## 2. Entorno del usuario y restricciones

| Elemento | Valor |
|---|---|
| Sistema | Windows 11 |
| Python | 3.13.x |
| Flet | **1.0.4** (fijado: `flet==1.0.4`, `flet-audio==1.0.4`) |
| Flutter (instalado por `flet build`) | 3.44.8 |
| JDK / Android SDK | JDK 17; plataforma Android 35 (compile/target 36 en el build de Flet; minSdk 24) |
| Editor | VS Code (Pylance) |

Restricciones importantes:

- **`flet build apk` tarda varios minutos** y a veces falla en Windows con «being used by another process» (Gradle/antivirus).
  `build_android.bat` ya cierra procesos de Gradle, reintenta una vez y compila desde una copia temporal.
- **No existe FFmpeg en Android.** Por eso Android descarga **M4A (AAC nativo)** sin recodificar y etiqueta con mutagen; Windows convierte a **MP3 192 kbps** con FFmpeg.
- **yt-dlp puede exigir un runtime de JavaScript** (Deno, Node, QuickJS…) para YouTube. En Windows funciona para el usuario; en Android no hay runtime
  y hay una línea comentada (`player_client`) en `adapters/android/downloader.py` como punto de ajuste si las descargas fallan.
- **El entorno donde se desarrolló el código** (sandbox Linux) no tenía Flutter ni el SDK de Android completo.
  Se pudo: ejecutar Python, compilar el **Java** contra el `android.jar` real (API 35) con stubs de Flutter, y simular Flet con páginas falsas.
  **No se pudo**: compilar Dart/Gradle, generar el APK, ni ejecutar nada en un teléfono.

---

## 3. Estado actual

### 3.1 Confirmado por el usuario (lo probó y dijo «todo bien»)

- Windows: descarga, conversión a MP3, biblioteca, reproductor (pygame), `.exe` con `flet pack`.
- Android: APK compila e instala; descarga M4A; biblioteca; reproductor con `flet-audio`; playlists; aleatorio; portadas; borrar canciones;
  rediseño de interfaz (incluida la corrección del teclado); **la extensión `flet-media-session` compiló**, muestra la notificación con botones y la música
  **sí sigue en segundo plano y con la pantalla bloqueada** (hasta que ocurre el bug de la sección 4).

### 3.2 Escrito y probado solo con simulaciones (no confirmado en dispositivo)

- **Vigilante de audio, recuperación, detección de pausas externas, renovación del motor en segundo plano y diálogo de Diagnóstico** (sección 4).
  Probado con pruebas unitarias/simuladas (11 escenarios pasan), **nunca en un teléfono**.
- **Controles multimedia de Windows (SMTC)** vía `winrt`: nombres de API verificados contra los paquetes, **no probado en Windows**.

### 3.3 Pendiente / no iniciado

Ver backlog en la sección 10.

---

## 4. BUG ABIERTO (prioridad 1): el audio se detiene fuera de la app

### 4.1 Reporte del usuario (textual)

> «Cada vez que se reproduce la canción fuera de la app, a la 4.ª o 5.ª canción se deja de escuchar, pero la barra de tiempo sigue avanzando.
> Esto solo pasa fuera de la app; cuando se está usando todo está correcto.»

### 4.2 Qué se sabe

- La «barra de tiempo» de la notificación **la avanza el sistema** por sí mismo: se le da una posición y velocidad 1.0 y la interpola.
  **Que avance no prueba que el audio suene ni que Python esté vivo.** Si Python/Dart dejan de actualizar el estado, la barra seguirá corriendo.
- En Flet 1.0.4 el control `Audio` (`flet-audio`) **no reenvía a Python los errores del motor nativo ni la pérdida del foco de audio**.
  Si el reproductor nativo (`audioplayers` sobre `MediaPlayer`) falla o es pausado por el sistema, deja de emitir eventos y Python sigue creyendo que suena.
- Transporte Dart↔Python en Android: es un **puente FFI en el mismo proceso** (serious_python), no un socket. Por eso la teoría de «el socket se cae en segundo plano» es poco probable.
- Servicios de Flet (`Audio`, `MediaSession`…) se gestionan por listeners de controles, **no dependen de que se dibujen fotogramas**.

### 4.3 Hipótesis (de más a menos probable)

1. **Fallo silencioso del motor nativo o pausa por pérdida de foco de audio** (`AUDIOFOCUS_LOSS…` → `audioplayers` hace `pause()`), sin aviso a Python.
2. **Se pierde el evento `completed`** y Python nunca avanza a la siguiente pista.
3. **Acumulación de recursos por cada cambio de `src`** (reproductores nativos que no se liberan) que solo se manifiesta tras 4–5 pistas en segundo plano.
4. **Congelación de Python/Dart en segundo plano** (Doze, optimización de batería del fabricante) — el servicio en primer plano y el wake lock deberían mitigarlo.
5. **El motor de Flutter se destruye** (Activity destruida): en ese caso el plugin detiene la notificación, así que no encaja con el síntoma (la notificación seguía).

No se identificó la causa real. Se implementó una defensa en profundidad + instrumentación (4.4).

### 4.4 Lo implementado para este bug (último trabajo; **sin probar en teléfono**)

Archivo: `mimusica/adapters/android/player.py` (clase `ReproductorFlet`).

- **Vigilante** (`_vigilar` / `_revisar` / `_recuperar`), un bucle cada 1 s mientras debería sonar:
  - Si pasan **≥ 3.5 s sin ningún evento** del motor → *intento 1*: `audio.resume()`; si siguen sin llegar eventos → *intento 2*: **recrear el control `Audio`**
    (quitarlo de `page.services`, crear uno nuevo con la ruta o los bytes, y volver con `seek` a la posición); si tampoco → muestra error y pone la UI en pausa.
  - **Fin de pista inferido:** si la última posición está a ≤ 2 s de la duración y pasan > 2.5 s sin eventos, se marca `terminado` aunque no llegara `completed`.
- **Pausas externas:** los estados `paused/stopped` que no provocamos nosotros se tratan como «el sistema pausó el audio» y se reflejan en la UI
  (`tomar_cambio_externo()` → `"pausa"` / `"reanuda"`). Los eventos que siguen a una orden nuestra se ignoran durante 1.5 s (`VENTANA_EVENTOS_PROPIOS_S`).
- **Renovación preventiva:** si la app está en segundo plano (la UI llama a `en_segundo_plano(True/False)` según `page.on_app_lifecycle_state_change`),
  **cada 3 pistas se recrea el control `Audio`** en vez de solo cambiar `src` (`PISTAS_ENTRE_RECREACIONES`).
- **Diagnóstico:** `mimusica/core/diagnostico.py` (búfer en memoria de ~400 eventos). Botón con icono de bicho en la cabecera → diálogo con el registro y
  «Copiar todo». Registra eventos del motor, ciclo de vida, botones de la notificación, estados enviados a la notificación y acciones de la app.

### 4.5 Siguientes pasos recomendados

1. **Pedir al usuario el registro** (icono de bicho → «Copiar todo») justo después de reproducir ~6 canciones con la pantalla bloqueada. Con él se distingue:
   - Aparecen líneas `vigilante: sin eventos…` → el vigilante detectó y quizá recuperó el silencio (¿se oyó otra vez?).
   - Aparecen `estado paused` sin acción nuestra / `foco de audio perdido` → causa: foco de audio.
   - **No hay eventos nuevos mientras la app está en segundo plano** (ni del motor ni del vigilante) → Python/Dart están congelados; el vigilante no puede ayudar.
2. **Si el vigilante no basta (o Python se congela en segundo plano), el arreglo de fondo es mover la reproducción al servicio nativo.**
   Hoy la extensión solo *refleja* el estado; el audio lo reproduce `flet-audio`. Un diseño robusto: que `MediaPlaybackService` (Java) reproduzca el audio con
   `MediaPlayer`/ExoPlayer, mantenga la cola y avance de pista **sin depender de Python**, y que Python solo mande la lista/comandos. Es un cambio grande y habrá
   que compilarlo con el usuario, pero elimina toda la clase de fallos «Dart/Python dormido».
3. Revisar el uso de `AudioContext` de audioplayers (`stayAwake`, foco de audio): `flet-audio` 1.0.4 no lo expone; haría falta tocar el Dart de la extensión o usar el motor nativo propio.

---

## 5. Arquitectura

Regla de dependencias: **`ui` → `core` ← `adapters`**. El núcleo no importa Flet, pygame ni nada de plataforma. `bootstrap.py` es el único sitio que elige adaptadores.

```
main.py                         # punto de entrada: ft.run(main) -> mimusica.ui.app.main(page, crear_plataforma())
build_windows.bat               # flet pack -D (carpeta) + copia tools/ (FFmpeg)
build_android.bat               # copia limpia a %TEMP%, cierra Gradle, flet build apk (+1 reintento)
pyproject.toml                  # SOLO para "flet build apk" (ASCII a propósito); dependencias + [tool.flet.dev_packages]
requirements.txt                # dependencias de escritorio (flet, yt-dlp[default], mutagen, pygame)
requirements-multimedia.txt     # opcional Windows: paquetes winrt para SMTC
tools/                          # ffmpeg.exe, ffprobe.exe (NO se suben a git); LEEME.txt
extensions/
  flet_media_session-0.1.0-py3-none-any.whl     # extensión de Android ya empaquetada (la usa el build)
  flet-media-session/                           # su código fuente (Python + Dart + Java)
mimusica/
  bootstrap.py                  # es_android() y crear_plataforma()
  core/                         # LÓGICA PURA
    models.py                   # Cancion, Playlist
    ports.py                    # Protocolos Descargador y Reproductor; dataclass Plataforma
    urls.py, errors.py, formatting.py
    diagnostico.py              # registro en memoria para depurar en el teléfono
    services/library.py         # escaneo, lectura de etiquetas (mutagen), eliminar_archivo
    services/queue.py           # ColaReproduccion (aleatorio sin repetir, quitar, anterior/siguiente)
    services/playlists.py       # RepositorioPlaylists (JSON atómico; guarda NOMBRES de archivo)
    services/covers.py          # leer_portada (APIC de MP3, covr de M4A)
  adapters/
    windows/  downloader.py (yt-dlp+FFmpeg→MP3), player.py (pygame), storage.py, tools.py (localize_ffmpeg), media_controls.py (SMTC)
    android/  downloader.py (yt-dlp sin FFmpeg→M4A), player.py (flet-audio + vigilante), media_controls.py (extensión), storage.py
  ui/
    app.py                      # ~1100 líneas: toda la lógica de pantallas y el diseño responsivo (candidato a dividir)
    player_views.py             # BarraEscritorio, MiniReproductor, ReproductorCompleto (+ dataclass Acciones)
    theme.py                    # colores y relleno()
```

### 5.1 Patrón clave: «vistas» que se actualizan todas por igual

`ui/app.py` mantiene una lista `vistas` (barra de escritorio, mini, pantalla completa y, si la plataforma lo da, los controles multimedia del sistema)
y los actualiza con `en_todas("pista" | "portada" | "progreso" | "tiempo" | "reproduciendo" | "aleatorio" | "cargando", …)`.
Cualquier objeto con esos métodos puede ser una vista. Así la notificación de Android y el SMTC de Windows son «una vista más».

### 5.2 Puertos (`core/ports.py`)

- `Reproductor`: `activo, reproducir(ruta, inicio_ms), pausar, reanudar, detener, saltar(ms), posicion_ms, terminado, poner_volumen`.
  Opcionales que la UI usa con `getattr`: `liberar()`, `cargando()`, `tomar_error()`, `tomar_cambio_externo()`, `en_segundo_plano(bool)`.
- `Descargador`: `ocupado, problema_de_entorno(), iniciar(url, destino), cancelar()`; se comunica por callbacks `on_estado/on_progreso/on_fin/on_error`.
- `Plataforma`: `nombre, permite_elegir_carpeta, carpeta_descargas(), carpeta_datos(), crear_descargador, crear_reproductor(page), extensiones, crear_controles_multimedia(pedir, page)`.
  Windows: `.mp3`, Descargas del sistema, `%APPDATA%\MiMusica`. Android: `.m4a`, almacenamiento **privado** de la app (`FLET_APP_STORAGE_DATA/musica`).

### 5.3 Flujo de reproducción (en `ui/app.py`)

- `reproducir_actual()` → `motor.reproducir(...)` en un hilo → actualiza vistas → lee la portada después (para no retrasar el audio).
- `bucle_reproduccion()` (cada 0.25 s): cambios externos → errores del motor → `motor.terminado()` → `pista_terminada()`; estado de «cargando»; progreso.
- `pista_terminada()` pasa a la siguiente de la cola (`ColaReproduccion`) o cierra la sesión multimedia.
- Acciones de la notificación/SMTC llegan a `desde_multimedia(accion, valor)`: `play, pause, siguiente, anterior, stop, seek`.
- Teclado en pantalla (móvil): se oculta cabecera/mini/navegación si `page.media.view_insets.bottom > 0` o la altura cae por debajo del 72 % de la máxima vista.

---

## 6. La extensión `flet-media-session` (Android)

Servicio en primer plano (`mediaPlayback`) + `MediaSession` + notificación `MediaStyle`. **No reproduce audio**: refleja lo que Python le dice y devuelve los botones.

- **Python** (`src/flet_media_session/`): `MediaSession(ft.Service)` con `request_permissions()`, `set_state(title, artist, album, duration_ms, position_ms, playing, art_path)`,
  `stop()` y evento `on_action` (`MediaActionEvent.action ∈ play|pause|next|previous|stop|seek`, `.position` en ms).
  **No llames `update()` a un método propio:** choca con `Control.update()`; por eso se llama `set_state`.
- **Dart** (`src/flutter/flet_media_session/lib/…`): `MediaSessionService extends FletService`; puente por `MethodChannel('mimusica/media_session')`
  (`setState`, `stop`, `requestPermissions`; nativo→Dart: `onAction`). Calcado de la estructura de `flet-audio`.
- **Java** (`…/android/src/main/java/dev/mimusica/flet_media_session/`): `FletMediaSessionPlugin` (canal, permiso `POST_NOTIFICATIONS`),
  `MediaPlaybackService` (MediaSession, notificación con anterior / pausa-play / siguiente, portada, cronómetro, wake lock parcial mientras suena,
  `startForeground` con tipo `MEDIA_PLAYBACK`), `EstadoMedia`. Solo APIs del framework (sin Kotlin ni AndroidX) para no depender de versiones del toolchain.
- **Manifiesto del plugin:** permisos `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK`, `POST_NOTIFICATIONS`, `WAKE_LOCK` y el `<service>`; se fusionan solos.
- **Empaquetado:** `python -m build --wheel` (ver `extensions/flet-media-session/README.md`). La rueda contiene `flutter/flet_media_session/…`, que `flet build` copia al proyecto Flutter
  (así funciona `flet-audio`). En `pyproject.toml`: `dependencies = [..., "flet-media-session"]` y
  `[tool.flet.dev_packages] flet-media-session = "extensions/flet_media_session-0.1.0-py3-none-any.whl"` (Flet lo convierte en ruta `file:///` válida; apunta a la **rueda**, no a la carpeta, porque pip corre con `--only-binary :all:`).
- **Si cambias el Java/Dart/Python de la extensión, reconstruye la rueda** y reemplaza la de `extensions/`.
- Comportamiento: si el usuario cierra la app desde «recientes», el motor de Flutter se destruye y el plugin detiene el servicio (el audio muere con el motor). Con Android 13+ pide el permiso de notificaciones al primer play; sin él el audio sigue pero la notificación no se ve.

---

## 7. Decisiones tomadas y por qué

| Decisión | Motivo |
|---|---|
| Python + Flet (no nativo) | Un solo código; yt-dlp es Python. Plan B para Android si Flet no basta: app nativa con `youtubedl-android`. |
| Windows usa **pygame**, no `flet-audio` | El control `Audio` falló en Windows por un error propio (se creaba sin `src`); pygame ya funcionaba y se quedó. |
| Android M4A sin FFmpeg | No hay FFmpeg en Android; AAC original sin recodificar + mutagen para etiquetas y portada. |
| Música en almacenamiento **privado** en Android | Android 11+ no permite escribir libremente en `/Download`. Exportar a carpeta pública es trabajo futuro (MediaStore o «acceso a todos los archivos»). |
| Playlists guardan **nombres de archivo** | Sobreviven a cambios de carpeta. |
| `ui/app.py` único y grande | Comparte mucho estado en cierres; se extrajeron las vistas del reproductor a `player_views.py`. Dividir más es backlog. |
| Java sin Kotlin ni AndroidX en la extensión | No acoplarse a versiones de Kotlin/AGP del toolchain de Flutter 3.44.8 que no se pudo inspeccionar. |
| `flet pack -D` (carpeta) para el `.exe` | Arranca más rápido y deja FFmpeg junto al `.exe`. `flet build windows` exigiría Visual Studio y no se probó. |
| iOS en pausa | Requiere Mac y cuenta de Apple; mismo problema de FFmpeg/JS que Android. |

---

## 8. Hechos aprendidos sobre Flet 1.0.4 (para no repetir errores)

**Cómo consultar el código fuente real** (en vez de adivinar): `raw.githubusercontent.com/flet-dev/flet/v1.0.4/packages/flet/lib/src/…` (Dart del cliente),
el sdist de `flet-audio` (`pip download flet-audio==1.0.4 --no-binary :all:`) contiene el Dart de la extensión, y `flet_cli/commands/build_base.py` en site-packages explica el build.

- **`flet-audio`:** el control `Audio` **exige `src` al montarse** (si no, `Exception("Audio must have src specified")` y todas las llamadas dan timeout de 30 s).
  `autoplay=True` reproduce al cambiar `src`; el evento `loaded` indica fuente lista; `src` acepta ruta/URL/bytes. **`BytesSource` no funciona en Windows.**
  El control `Audio` va en `page.services` (no en `overlay`). Eventos: `on_loaded, on_duration_change, on_state_change, on_position_change, on_seek_complete`; posición en segundos redondeados (≈1 evento/s).
- **Eventos con `control`:** comparar con identidad (`is`). Los controles de Flet son dataclasses con `__eq__` por valor: `x in lista` o `lista.remove(x)` pueden confundir dos controles distintos con las mismas propiedades.
- **API 1.x:** `ft.run(main)`; diálogos con `page.show_dialog()/pop_dialog()` (también SnackBar); `ft.Clipboard()` y `ft.FilePicker()` son servicios (`page.services.append`);
  `Button/FilledButton("texto", icon=…)`; `ft.Padding.symmetric`, `ft.Alignment.CENTER`, `ft.BoxFit.COVER`, `ft.Offset` + `animate_offset` para el deslizamiento de la pantalla completa;
  `TextField(border=ft.OutlineInputBorder(border_radius=…))` (el `border_radius` suelto está en desuso); `NavigationBar` + `NavigationBarDestination`; `ListView(on_scroll, scroll_interval)`.
- **Teclado en Android:** `page.media.view_insets.bottom` y `page.on_media_change`; respaldo por altura con `page.on_resize`.
- **Variables de entorno de Flet en móvil:** `FLET_PLATFORM` (`android`), `FLET_APP_STORAGE_DATA`, `FLET_APP_STORAGE_TEMP`.
- **Extensiones de usuario:** `flet build` copia las carpetas `flutter/<paquete>` de los paquetes Python instalados y las registra solas; el `pubspec.yaml` de la extensión usa
  `flet: path: ../../../../../../../packages/flet` (Flet lo sobrescribe). Ver sección 6.
- **Hilos:** actualizar la UI desde un hilo con `page.run_task(async_fn)` (seguro). El código usa el helper `seguro()`.
- **Hubo un intento de usar un servidor HTTP local** para servir audio al motor: no hizo falta; el problema real era el `src` vacío.
- **Windows:** `flet pack` empaqueta con PyInstaller; el antivirus/SmartScreen puede marcar el `.exe`. Para actualizar yt-dlp hay que reconstruir el `.exe`.

---

## 9. Cómo compilar y probar

**Entorno de desarrollo (Windows):**
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt           # + requirements-multimedia.txt (opcional, SMTC)
# copiar ffmpeg.exe y ffprobe.exe a tools/
python main.py                            # o: flet run main.py
```
**`.exe`:** doble clic en `build_windows.bat` → `dist\MiMusica\MiMusica.exe` (comprimir la carpeta completa; `tools/` debe ir junto al exe).
**APK:** modo desarrollador de Windows activo; doble clic en `build_android.bat` → `dist\*.apk`. Si falla, pedir el texto desde `FAILURE`/primer `Error`.

**Cómo se probó en el entorno de desarrollo (útil para seguir):**
- `python -m pyflakes mimusica main.py` (la extensión da un aviso inocuo en `types.py`).
- **Páginas falsas de Flet** (`FakePage` con `services`, `run_task` → `asyncio.ensure_future`, `show_dialog`, `media`) y un `FakeMotor`/`FakeMM` para ejecutar `mimusica.ui.app.main()` y
  recorrer el árbol de controles buscando por tipo/propiedad; así se probaron reproducir, aleatorio, playlists, borrar, teclado, paginación, notificación y vigilante.
  Para el vigilante: parchear `fta.Audio.resume/pause/seek/update` y las constantes de tiempo del módulo.
- **Java:** compilar con `javac` contra `android.jar` (API 35, repositorio Sable/android-platforms) más stubs mínimos de `io.flutter.*` y `R`.
- Los **MP3/M4A de prueba** se generan con `ffmpeg -f lavfi -i "sine=…"` (con y sin portada incrustada).

---

## 10. Backlog priorizado

1. **(P1) Bug del audio en segundo plano** (sección 4): obtener el registro de Diagnóstico y decidir entre afinar el vigilante o mover la reproducción al servicio nativo.
2. Confirmar en el teléfono el vigilante y la renovación del motor; ajustar umbrales (`UMBRAL_SILENCIO_S`, `PISTAS_ENTRE_RECREACIONES`) con datos reales.
3. **Descargas en segundo plano en Android** (hoy se pausan al bloquear la pantalla): ampliar el servicio en primer plano para cubrirlas.
4. **Exportar música a la carpeta pública** en Android (MediaStore o permiso de acceso a todos los archivos).
5. **Descargas en Android y runtime de JavaScript de YouTube** (si fallan, probar otro `player_client` o un runtime ligero tipo QuickJS).
6. Botón **Atrás** de Android con la pantalla completa abierta (no probado: ¿cierra la vista o sale de la app?).
7. Dividir `ui/app.py` en componentes (descargas, biblioteca, reproductor) y **añadir pruebas automáticas** al repositorio (hoy las pruebas viven fuera).
8. Mecanismo de **actualización de yt-dlp** dentro del `.exe`; instalador (Inno Setup) y firma del ejecutable.
9. Probar en Windows los controles SMTC (`requirements-multimedia.txt`) y, si funcionan, documentar/empaquetar mejor con PyInstaller.
10. **iOS** (en pausa por indicación del usuario): reutilizar adaptadores de Android; requiere Mac, cuenta de Apple y firma.
11. Publicación en GitHub: completar URL del repo, capturas y archivo `LICENSE` (el README dice «Por definir»); distribuir APK/exe como **Release**, no dentro del repo.

---

## 11. Archivos para leer primero

1. `mimusica/adapters/android/player.py` — vigilante y recuperación (donde está el bug abierto).
2. `mimusica/ui/app.py` — `reproducir_actual`, `bucle_reproduccion`, `pista_terminada`, `desde_multimedia`, `ajustar_diseno`, diálogo de Diagnóstico.
3. `mimusica/adapters/android/media_controls.py` y `extensions/flet-media-session/` — notificación y servicio en primer plano.
4. `mimusica/core/ports.py` — contratos entre capas.
5. `README.md` — instrucciones para el usuario final, solución de problemas y aviso legal.

---

## 12. Advertencias finales

- El historial de este proyecto incluye **diagnósticos equivocados corregidos después** (p. ej. se creyó que el fallo de `flet-audio` en Windows era por bytes/URL; era un `src` vacío).
  Antes de proponer una causa, apóyate en el código fuente o en un registro del dispositivo.
- Nunca entregues cambios sin regenerar el zip completo y **sin decir qué quedó sin probar**.
- Si el entorno de trabajo del asistente se reinicia y pierde archivos, la fuente de verdad es el zip entregado al usuario.
