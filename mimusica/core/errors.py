"""Traducción de errores técnicos de yt-dlp a mensajes en español."""

from __future__ import annotations

import re


def mensaje_error_amigable(error: Exception | str) -> str:
    """Traduce los errores técnicos de yt-dlp a mensajes claros en español."""
    crudo = re.sub(r"\x1b\[[0-9;]*m", "", str(error))  # quita colores ANSI
    t = crudo.lower()
    if crudo.startswith("Spotify:"):
        return crudo
    if any(s in t for s in (
        "unable to download", "getaddrinfo", "network is unreachable", "timed out",
        "connection", "urlopen error", "name resolution", "temporary failure",
    )):
        return "No hay conexión a internet o no se pudo contactar con YouTube. Revisa tu red e inténtalo de nuevo."
    if "private video" in t or "video is private" in t:
        return "El video es privado y no se puede descargar."
    if "confirm your age" in t or "age-restricted" in t or "age restricted" in t:
        return "El video tiene restricción de edad y no se puede descargar sin iniciar sesión."
    if "members-only" in t or "members only" in t or "join this channel" in t:
        return "Este contenido es exclusivo para miembros del canal."
    if "http error 429" in t or "too many requests" in t:
        return "YouTube está limitando las peticiones. Espera unos minutos e inténtalo otra vez."
    if "sign in to confirm" in t:
        return "YouTube pide verificación de inicio de sesión para este contenido."
    if "premieres in" in t or "live event will begin" in t:
        return "El video aún no se ha estrenado."
    if "video unavailable" in t or "not available" in t or "has been removed" in t or "no longer available" in t:
        return "El video no está disponible (fue eliminado o está bloqueado en tu región)."
    if "unsupported url" in t or "is not a valid url" in t:
        return "El enlace no es válido o está roto."
    if "ffmpeg" in t or "ffprobe" in t:
        return "No se encontró FFmpeg/FFprobe. Coloca ffmpeg.exe y ffprobe.exe junto a la aplicación."
    limpio = crudo.replace("ERROR:", "").strip()
    return f"Ocurrió un error inesperado: {limpio[:250]}"
