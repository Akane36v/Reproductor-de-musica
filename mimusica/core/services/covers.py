"""Lectura de la portada incrustada en un archivo de audio (MP3: APIC, M4A: covr)."""

from __future__ import annotations

from mutagen import File as MutagenFile


def leer_portada(ruta: str) -> bytes | None:
    """Devuelve los bytes de la imagen (JPG/PNG) o None si el archivo no tiene portada."""
    try:
        audio = MutagenFile(ruta)
        etiquetas = getattr(audio, "tags", None)
        if not etiquetas:
            return None
        if hasattr(etiquetas, "getall"):                 # ID3 (MP3)
            imagenes = etiquetas.getall("APIC")
            if imagenes:
                return bytes(imagenes[0].data)
        elif "covr" in etiquetas:                        # MP4 (M4A)
            portadas = etiquetas["covr"]
            if portadas:
                return bytes(portadas[0])
    except Exception:
        pass
    return None
