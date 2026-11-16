"""Paleta y constantes visuales (tema oscuro estilo Spotify / YouTube Music)."""

COLOR_FONDO = "#111111"
COLOR_SUPERFICIE = "#161616"
COLOR_SUPERFICIE_2 = "#272727"
COLOR_ACENTO = "#65D46E"
COLOR_TEXTO = "#F5F5F5"
COLOR_TEXTO_SUAVE = "#ADADAD"
COLOR_CABECERA = "#60451F"
COLOR_MINI = "#222936"
COLOR_ERROR = "#FF5252"

# A partir de este ancho (px) se usa el diseño de escritorio de dos paneles;
# por debajo se usa el diseño vertical para móvil con barra de navegación.
ANCHO_MODO_ESCRITORIO = 900

COLOR_FONDO_SUAVE = "#49361E"   # tono del degradado de la pantalla de reproducción


def relleno(horizontal: int, vertical: int):
    """Padding simétrico compatible con distintas versiones de Flet."""
    import flet as ft
    return ft.Padding.symmetric(horizontal=horizontal, vertical=vertical) if hasattr(ft, "Padding") else horizontal
