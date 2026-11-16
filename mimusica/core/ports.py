"""
Puertos (interfaces) del núcleo.

La interfaz (ui/) solo conoce estos contratos. Cada plataforma (adapters/windows,
adapters/android...) los implementa a su manera y se ensambla en bootstrap.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class Descargador(Protocol):
    """Descarga audio en segundo plano y avisa por callbacks."""

    @property
    def ocupado(self) -> bool: ...

    def problema_de_entorno(self) -> str | None:
        """None si todo está listo; si no, un mensaje claro (p. ej. falta FFmpeg)."""
        ...

    def iniciar(self, url: str, destino: Path) -> None: ...

    def cancelar(self) -> None: ...


class Reproductor(Protocol):
    """Reproduce un archivo de audio local."""

    @property
    def activo(self) -> bool: ...

    def reproducir(self, ruta: str, inicio_ms: int = 0) -> None: ...
    def pausar(self) -> None: ...
    def reanudar(self) -> None: ...
    def detener(self) -> None: ...
    def saltar(self, ms: int) -> None: ...
    def posicion_ms(self) -> int: ...
    def terminado(self) -> bool: ...
    def poner_volumen(self, valor: float) -> None: ...

    # Opcionales (la interfaz los usa solo si existen): liberar() suelta el archivo para poder
    # borrarlo; cargando() indica que el motor aún no ha empezado a sonar; tomar_error() avisa
    # de un fallo ya mostrado al usuario.


@dataclass
class Plataforma:
    """Todo lo que cambia entre Windows y Android, agrupado en un solo objeto."""

    nombre: str
    permite_elegir_carpeta: bool
    carpeta_descargas: Callable[[], Path]
    # Carpeta privada de la app para guardar datos propios (playlists.json)
    carpeta_datos: Callable[[], Path]
    # Recibe on_estado, on_progreso, on_fin, on_error (por nombre) y devuelve un Descargador
    crear_descargador: Callable[..., Descargador]
    # Recibe la página de Flet (algunos motores, como el de Android, la necesitan).
    # Puede lanzar excepción si no hay motor de audio disponible.
    crear_reproductor: Callable[[Any], Reproductor]
    # Formatos de audio que esta plataforma descarga y sabe reproducir
    extensiones: tuple[str, ...] = (".mp3",)
    # Controles multimedia del sistema (opcional). Recibe pedir(accion, valor=0) con las acciones
    # "play", "pause", "siguiente", "anterior", "stop" y "seek" (valor en ms), y la página de Flet.
    # Devuelve un objeto con los mismos métodos de actualización que las vistas del reproductor
    # (pista, portada, progreso, reproduciendo...).
    crear_controles_multimedia: Callable[[Callable[..., None], Any], Any] | None = None
