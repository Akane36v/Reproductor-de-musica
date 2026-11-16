from dataclasses import dataclass
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from flet_media_session.media_session import MediaSession  # noqa

__all__ = ["MediaActionEvent"]


@dataclass
class MediaActionEvent(ft.Event["MediaSession"]):
    """Un boton de la notificacion multimedia (o de la pantalla de bloqueo) fue pulsado."""

    action: str
    """Uno de: "play", "pause", "next", "previous", "stop", "seek"."""

    position: int = 0
    """Solo para "seek": la posicion pedida, en milisegundos."""
