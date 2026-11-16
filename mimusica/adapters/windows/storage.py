"""Carpeta de descargas del usuario en Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _descargas_windows() -> Path | None:
    """Pregunta a Windows cuál es la carpeta 'Descargas' real (puede estar redirigida)."""
    try:
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
        guid = GUID(
            0x374DE290, 0x123F, 0x4565,
            (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
        )
        puntero = ctypes.c_wchar_p()
        resultado = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(puntero)
        )
        if resultado == 0 and puntero.value:
            return Path(puntero.value)
    except Exception:
        pass
    return None


def carpeta_descargas() -> Path:
    """Carpeta 'Descargas' real del usuario (con respaldo a ~/Downloads)."""
    if sys.platform == "win32":
        ruta = _descargas_windows()
        if ruta:
            return ruta
    return Path.home() / "Downloads"


def carpeta_datos() -> Path:
    """Datos de la app (playlists): %APPDATA%\\MiMusica, con respaldo en la carpeta del usuario."""
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home()) / "MiMusica"
