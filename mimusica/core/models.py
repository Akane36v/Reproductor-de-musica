"""Modelos de datos del núcleo (sin dependencias de interfaz ni de plataforma)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Cancion:
    """Una canción de la biblioteca local."""
    ruta: str
    titulo: str
    artista: str
    album: str
    duracion: float  # segundos


@dataclass
class Playlist:
    """Lista de reproducción. Guarda NOMBRES de archivo (no rutas) para sobrevivir a cambios de carpeta."""
    id: str
    nombre: str
    archivos: list[str]
