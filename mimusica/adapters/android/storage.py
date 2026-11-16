"""Carpeta de música en Android: almacenamiento privado de la app (no requiere permisos)."""

from __future__ import annotations

import os
from pathlib import Path


def carpeta_musica() -> Path:
    """
    FLET_APP_STORAGE_DATA es un directorio privado, persistente y ya creado por Flet
    (en Android: /data/data/<paquete>/files/data). Escribir ahí no necesita permisos.
    Para exportar a la carpeta pública Descargas/Música se necesita una fase posterior
    (MediaStore o permiso de "acceso a todos los archivos").
    """
    base = os.environ.get("FLET_APP_STORAGE_DATA")
    ruta = Path(base) / "musica" if base else Path.home() / "musica"
    try:
        ruta.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return ruta


def carpeta_datos() -> Path:
    """Datos de la app (playlists): raíz del almacenamiento privado de Flet."""
    base = os.environ.get("FLET_APP_STORAGE_DATA")
    return Path(base) if base else Path.home() / ".mimusica"
