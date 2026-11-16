# flet-media-session

Extension de Flet (solo Android) que mantiene la musica sonando con la app en segundo plano o con
la pantalla bloqueada, y muestra una notificacion multimedia con portada, titulo, artista,
barra de progreso (minuto y segundo) y botones de anterior, pausar/reanudar y siguiente.

Esta extension NO reproduce audio: solo representa en el sistema lo que otra parte de la app
(por ejemplo flet-audio) esta reproduciendo y avisa a Python de los botones pulsados.

```python
import flet as ft
import flet_media_session as fms

sesion = fms.MediaSession(on_action=lambda e: print(e.action, e.position))
page.services.append(sesion)

await sesion.request_permissions()
await sesion.set_state(title="Cancion", artist="Artista", duration_ms=200000,
                       position_ms=0, playing=True, art_path="/ruta/portada.jpg")
await sesion.stop()
```

Acciones que llegan a `on_action`: `play`, `pause`, `next`, `previous`, `stop`, `seek`
(con `position` en milisegundos).

## Reconstruir la rueda

```
cd extensions/flet-media-session
pip install build
python -m build --wheel -o ..
```
La rueda contiene la parte Python y, en `flutter/flet_media_session/`, el plugin de Flutter
(Dart + Java) que `flet build apk` compila dentro de la aplicacion.
