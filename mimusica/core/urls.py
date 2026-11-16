"""Validación y análisis de enlaces de YouTube y Spotify."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

HOSTS_VALIDOS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def recurso_spotify(texto: str) -> tuple[str, str] | None:
    """Solo canciones y playlists públicas; descarta parámetros de seguimiento."""
    url = (texto or "").strip()
    uri = re.fullmatch(r"spotify:(track|playlist):([A-Za-z0-9]{22})", url)
    if uri:
        return uri.group(1), uri.group(2)
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        partes = urlparse(url)
        if (partes.hostname or "").lower() != "open.spotify.com":
            return None
        if partes.username or partes.password or partes.port not in (None, 80, 443):
            return None
    except ValueError:
        return None
    ruta = re.fullmatch(r"/(?:intl-[a-zA-Z-]+/)?(?:embed/)?(track|playlist)/([A-Za-z0-9]{22})/?", partes.path)
    return (ruta.group(1), ruta.group(2)) if ruta else None


def validar_url(texto: str) -> str | None:
    """Devuelve un enlace compatible normalizado, o None."""
    url = (texto or "").strip()
    if not url or any(c.isspace() for c in url):
        return None
    spotify = recurso_spotify(url)
    if spotify:
        return f"https://open.spotify.com/{spotify[0]}/{spotify[1]}"
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        partes = urlparse(url)
        host = (partes.hostname or "").lower()
    except ValueError:
        return None
    if host not in HOSTS_VALIDOS:
        return None

    consulta = parse_qs(partes.query)
    ruta = partes.path
    if host == "youtu.be":
        return url if ruta.strip("/") else None
    if ruta == "/watch":
        return url if ("v" in consulta or "list" in consulta) else None
    if ruta == "/playlist":
        return url if "list" in consulta else None
    # Shorts, directos, embeds y /browse/ (álbumes de YouTube Music)
    if ruta.startswith(("/shorts/", "/live/", "/embed/", "/v/", "/browse/")):
        return url
    return None


def es_mix_automatico(url: str) -> bool:
    """
    Los 'Mix' automáticos de YouTube (list=RD...) acompañan a un video suelto y
    son casi infinitos. Si el enlace tiene video + mix, se baja solo el video.
    """
    consulta = parse_qs(urlparse(url).query)
    lista = (consulta.get("list") or [""])[0]
    return "v" in consulta and lista.startswith("RD")
