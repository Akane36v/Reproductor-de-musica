"""
Controles multimedia de Android: notificación flotante con portada, tiempo y botones
(anterior, pausar/reanudar, siguiente), pantalla de bloqueo y audio en segundo plano.

Usa la extensión propia "flet-media-session" (servicio en primer plano + MediaSession).
Esta clase solo refleja en el sistema lo que la app está reproduciendo, con los mismos
métodos de actualización que las vistas del reproductor (pista, portada, progreso,
reproduciendo...), y reenvía los botones pulsados a la app mediante pedir(accion, valor).

Si la extensión no está disponible (p. ej. al probar en el escritorio), todo se vuelve
inofensivo y la app funciona igual.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

from mimusica.core.diagnostico import registrar

# Nombre de la acción de la extensión -> acción de la app
ACCIONES = {
    "play": "play",
    "pause": "pause",
    "next": "siguiente",
    "previous": "anterior",
    "stop": "stop",
    "seek": "seek",
}
TITULO_VACIO = "Nada en reproducción"


class ControlesMultimediaAndroid:
    def __init__(self, pedir, page):
        self._pedir = pedir
        self._page = page
        self._sesion = None
        self.error: str | None = None   # motivo por el que no se activó (diagnóstico)

        self._titulo = ""
        self._artista = ""
        self._duracion_ms = 0
        self._reproduciendo = False
        self._pos_base = 0               # última posición conocida (ms)
        self._t0 = time.monotonic()      # instante en que se conoció esa posición
        self._ruta_portada: str | None = None
        self._n_portada = 0
        self._pendiente = False          # hay un envío programado (junta cambios seguidos)
        self._permiso_pedido = False

        try:
            import flet_media_session as fms
            self._sesion = fms.MediaSession(on_action=self._al_accion)
            page.services.append(self._sesion)
        except Exception as ex:  # extensión no instalada o no disponible
            self.error = f"{type(ex).__name__}: {ex}"

    @property
    def activo(self) -> bool:
        return self._sesion is not None

    # ---- botones de la notificación (llegan como evento de la extensión) -----------
    def _al_accion(self, e):
        accion = ACCIONES.get(getattr(e, "action", ""))
        if accion:
            try:
                self._pedir(accion, int(getattr(e, "position", 0) or 0))
            except Exception:
                pass

    # ---- posición estimada (el sistema la avanza solo mientras suena) ---------------
    def _posicion(self) -> int:
        if self._reproduciendo:
            return self._pos_base + int((time.monotonic() - self._t0) * 1000)
        return self._pos_base

    def _fijar_posicion(self, ms: int):
        self._pos_base, self._t0 = max(int(ms), 0), time.monotonic()

    # ---- envío a la extensión ------------------------------------------------------------
    def _programar(self):
        """Programa UN envío en 120 ms: varios cambios seguidos (pista, portada, play) se juntan."""
        if self._sesion is None or self._pendiente:
            return
        self._pendiente = True
        try:
            self._page.run_task(self._enviar)
        except Exception:
            self._pendiente = False

    async def _enviar(self):
        await asyncio.sleep(0.12)
        self._pendiente = False
        if not self._titulo:
            return
        try:
            registrar("notificación", f"estado: {'sonando' if self._reproduciendo else 'pausa'} "
                                      f"pos={self._posicion() // 1000}s «{self._titulo}»")
            await self._sesion.set_state(
                title=self._titulo,
                artist=self._artista,
                duration_ms=self._duracion_ms,
                position_ms=self._posicion(),
                playing=self._reproduciendo,
                art_path=self._ruta_portada,
            )
        except Exception:
            pass  # un fallo de la notificación nunca debe afectar a la reproducción

    async def _pedir_permiso(self):
        """Android 13+: permiso de notificaciones. El audio en segundo plano funciona sin él."""
        try:
            await self._sesion.request_permissions()
        except Exception:
            pass

    async def _detener(self):
        try:
            await self._sesion.stop()
        except Exception:
            pass

    # ---- interfaz común de las vistas del reproductor ------------------------------------
    def pista(self, titulo: str, artista: str, duracion_s: float):
        if self._sesion is None:
            return
        self._titulo = "" if titulo == TITULO_VACIO else titulo
        self._artista = artista
        self._duracion_ms = int(duracion_s * 1000)
        self._ruta_portada = None
        self._fijar_posicion(0)
        if self._titulo:
            if not self._permiso_pedido:
                self._permiso_pedido = True
                self._page.run_task(self._pedir_permiso)
            self._programar()

    def portada(self, datos):
        if self._sesion is None or not self._titulo:
            return
        anterior = self._ruta_portada
        self._ruta_portada = None
        if datos:
            try:
                carpeta = Path(os.environ.get("FLET_APP_STORAGE_TEMP") or tempfile.gettempdir())
                self._n_portada += 1
                ruta = carpeta / f"portada_actual_{self._n_portada}.jpg"
                ruta.write_bytes(datos)
                self._ruta_portada = str(ruta)
            except OSError:
                self._ruta_portada = None
        if anterior and anterior != self._ruta_portada:
            try:
                Path(anterior).unlink()
            except OSError:
                pass
        self._programar()

    def reproduciendo(self, activo: bool):
        if self._sesion is None or activo == self._reproduciendo:
            return
        self._fijar_posicion(self._posicion())  # congela o reanuda desde donde iba
        self._reproduciendo = activo
        self._programar()

    def progreso(self, ms: int, max_ms: int):
        """Se llama 4 veces por segundo: solo se envía algo si hubo un salto (seek, cambio de pista)."""
        if self._sesion is None or not self._titulo:
            return
        if max_ms > 0:
            self._duracion_ms = max_ms
        if abs(ms - self._posicion()) > (1500 if self._reproduciendo else 500):
            self._fijar_posicion(ms)
            self._programar()

    def tiempo(self, ms: int): pass
    def aleatorio(self, activo: bool): pass
    def cargando(self, activo: bool): pass

    def cerrar(self):
        """Quita la notificación y detiene el servicio en primer plano."""
        if self._sesion is None:
            return
        self._titulo = ""
        self._reproduciendo = False
        self._page.run_task(self._detener)
