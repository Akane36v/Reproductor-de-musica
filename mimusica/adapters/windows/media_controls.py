"""
Controles multimedia de Windows (SMTC, "System Media Transport Controls").

Muestra en el panel de medios de Windows (al cambiar el volumen, en la pantalla de
bloqueo y en las teclas multimedia) la canción que suena, con los botones de pausar,
reanudar, siguiente y anterior. También atiende las teclas multimedia del teclado.

Es opcional: si los paquetes winrt no están instalados o algo falla, todos los métodos
se vuelven inofensivos y la app sigue funcionando igual. Instalación:
    pip install -r requirements-multimedia.txt

Tiene los mismos métodos de actualización que las vistas del reproductor (pista,
reproduciendo, ...), así que la app lo trata como una vista más.
"""

from __future__ import annotations


class ControlesMultimediaWindows:
    def __init__(self, pedir, page=None):
        """'pedir(accion)' se llama con "play", "pause", "siguiente", "anterior" o "stop"."""
        self._pedir = pedir
        self._smtc = None
        self._estados = None
        self.error: str | None = None   # motivo por el que no se activó (para diagnóstico)
        try:
            from winrt.windows.media import (
                MediaPlaybackStatus, MediaPlaybackType, SystemMediaTransportControlsButton,
            )
            from winrt.windows.media.playback import MediaPlayer

            self._Estado = MediaPlaybackStatus
            self._Tipo = MediaPlaybackType
            self._Boton = SystemMediaTransportControlsButton
            self._reproductor = MediaPlayer()                      # solo aporta los controles del sistema
            self._reproductor.command_manager.is_enabled = False   # los botones los gestionamos nosotros
            smtc = self._reproductor.system_media_transport_controls
            smtc.is_play_enabled = True
            smtc.is_pause_enabled = True
            smtc.is_next_enabled = True
            smtc.is_previous_enabled = True
            smtc.is_stop_enabled = True
            self._token = smtc.add_button_pressed(self._al_pulsar)
            self._smtc = smtc
        except Exception as ex:  # winrt no instalado o no disponible
            self.error = f"{type(ex).__name__}: {ex}"

    @property
    def activo(self) -> bool:
        return self._smtc is not None

    # ---- botones del sistema (llegan desde otro hilo) -------------------------
    def _al_pulsar(self, sender, args):
        try:
            b = self._Boton
            accion = {b.PLAY: "play", b.PAUSE: "pause", b.NEXT: "siguiente",
                      b.PREVIOUS: "anterior", b.STOP: "stop"}.get(args.button)
            if accion:
                self._pedir(accion)
        except Exception:
            pass

    # ---- interfaz común de las vistas del reproductor ------------------------
    def pista(self, titulo: str, artista: str, duracion_s: float):
        if not self._smtc:
            return
        try:
            self._smtc.is_enabled = True
            actualizador = self._smtc.display_updater
            actualizador.type = self._Tipo.MUSIC
            actualizador.music_properties.title = titulo
            actualizador.music_properties.artist = artista
            actualizador.update()
        except Exception:
            pass

    def reproduciendo(self, activo: bool):
        if not self._smtc:
            return
        try:
            self._smtc.playback_status = self._Estado.PLAYING if activo else self._Estado.PAUSED
        except Exception:
            pass

    def portada(self, datos): pass
    def progreso(self, ms: int, max_ms: int): pass
    def tiempo(self, ms: int): pass
    def aleatorio(self, activo: bool): pass
    def cargando(self, activo: bool): pass

    def cerrar(self):
        """Quita la ficha del panel de medios (cuando no queda ninguna canción)."""
        if not self._smtc:
            return
        try:
            self._smtc.is_enabled = False
        except Exception:
            pass
