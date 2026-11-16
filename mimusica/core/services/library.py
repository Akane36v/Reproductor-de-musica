"""Servicio de biblioteca: lectura de etiquetas y escaneo de la carpeta (MP3 y M4A)."""

from __future__ import annotations

import os
from pathlib import Path

from mutagen import File as MutagenFile

from mimusica.core.models import Cancion


def _primero(etiquetas, clave: str) -> str:
    """Primer valor de una etiqueta 'easy' (siempre son listas) o cadena vacía."""
    valor = etiquetas.get(clave) if etiquetas else None
    return str(valor[0]).strip() if valor else ""


def leer_cancion(ruta: Path) -> Cancion:
    """Lee título, artista, álbum y duración. Si falla, usa el nombre del archivo."""
    titulo, artista, album, duracion = ruta.stem, "Artista desconocido", "", 0.0
    try:
        audio = MutagenFile(str(ruta), easy=True)
        if audio is not None:
            duracion = float(getattr(audio.info, "length", 0) or 0)
            etiquetas = audio.tags
            titulo = _primero(etiquetas, "title") or titulo
            artista = _primero(etiquetas, "artist") or _primero(etiquetas, "albumartist") or artista
            album = _primero(etiquetas, "album")
    except Exception:
        pass  # archivo sin etiquetas o dañado: se muestra con los valores por defecto
    return Cancion(str(ruta), titulo, artista, album, duracion)


def escanear_biblioteca(carpeta: Path, extensiones: tuple[str, ...] = (".mp3",)) -> list[Cancion]:
    """Lista los archivos de audio de la carpeta (sin subcarpetas), los más recientes primero."""
    if not carpeta.is_dir():
        return []
    extensiones = tuple(e.lower() for e in extensiones)
    archivos: list[tuple[float, Path]] = []
    with os.scandir(carpeta) as it:
        for entrada in it:
            if entrada.is_file() and entrada.name.lower().endswith(extensiones):
                try:
                    archivos.append((entrada.stat().st_mtime, Path(entrada.path)))
                except OSError:
                    continue
    archivos.sort(key=lambda x: x[0], reverse=True)
    return [leer_cancion(ruta) for _, ruta in archivos]


def eliminar_archivo(ruta: Path) -> None:
    """Borra el archivo de audio. Si ya no existe se considera hecho; otros fallos lanzan OSError."""
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
