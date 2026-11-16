"""Localización de herramientas externas portátiles (FFmpeg) en Windows."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _directorio_base() -> Path:
    """Carpeta raíz de la app (funciona en script, PyInstaller y flet build)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]  # raíz del proyecto


def localize_ffmpeg() -> str | None:
    """
    Busca FFmpeg sin depender de variables de entorno.
    Devuelve la CARPETA que contiene ffmpeg y ffprobe, o None si no los encuentra.

    Orden de búsqueda:
      1. ./tools/ y ./tools/bin/ (recomendado)
      2. Raíz del proyecto, ./ffmpeg/bin/ , ./ffmpeg/ y ./bin/
      3. Rutas estándar del sistema
      4. El PATH (último recurso)
    """
    sufijo = ".exe" if os.name == "nt" else ""
    base = _directorio_base()

    candidatos: list[Path] = [
        base / "tools", base / "tools" / "bin",
        base, base / "ffmpeg" / "bin", base / "ffmpeg", base / "bin",
    ]

    # Carpeta temporal de PyInstaller, si existe
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos += [Path(meipass), Path(meipass) / "ffmpeg" / "bin"]

    # Rutas estándar
    if os.name == "nt":
        candidatos += [
            Path("C:/ffmpeg/bin"),
            Path("C:/Program Files/ffmpeg/bin"),
            Path("C:/Program Files (x86)/ffmpeg/bin"),
            Path.home() / "ffmpeg" / "bin",
        ]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidatos.append(Path(local) / "Microsoft" / "WinGet" / "Links")
    else:
        candidatos += [
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
            Path("/data/data/com.termux/files/usr/bin"),
        ]

    for carpeta in candidatos:
        if (carpeta / f"ffmpeg{sufijo}").is_file() and (carpeta / f"ffprobe{sufijo}").is_file():
            return str(carpeta)

    # Último recurso: PATH del sistema
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path and ffprobe_path:
        return str(Path(ffmpeg_path).parent)
    return None
