from typing import Optional

import flet as ft
from flet_media_session.types import MediaActionEvent


@ft.control("MediaSession")
class MediaSession(ft.Service):
    """
    Sesion multimedia de Android: servicio en primer plano + notificacion con controles.

    Solo tiene efecto en Android; en otras plataformas las llamadas no hacen nada.
    """

    on_action: Optional[ft.EventHandler[MediaActionEvent]] = None
    """Se dispara al pulsar un boton de la notificacion o de la pantalla de bloqueo."""

    async def request_permissions(self) -> bool:
        """
        Pide el permiso de notificaciones (Android 13 o superior).

        Returns:
            True si las notificaciones estan permitidas.
        """
        return bool(await self._invoke_method("request_permissions"))

    async def set_state(
        self,
        title: str,
        artist: str = "",
        album: str = "",
        duration_ms: int = 0,
        position_ms: int = 0,
        playing: bool = False,
        art_path: Optional[str] = None,
    ):
        """
        Muestra o actualiza la notificacion y mantiene vivo el servicio en primer plano.

        Args:
            title: Titulo de la cancion.
            artist: Artista.
            album: Album.
            duration_ms: Duracion total en milisegundos.
            position_ms: Posicion actual en milisegundos (el sistema la avanza solo mientras suena).
            playing: True si esta sonando; False si esta en pausa.
            art_path: Ruta de un archivo de imagen (JPG/PNG) con la portada.
        """
        await self._invoke_method(
            "set_state",
            {
                "title": title,
                "artist": artist,
                "album": album,
                "durationMs": int(duration_ms),
                "positionMs": int(position_ms),
                "playing": bool(playing),
                "artPath": art_path,
            },
        )

    async def stop(self):
        """Quita la notificacion y detiene el servicio en primer plano."""
        await self._invoke_method("stop")
