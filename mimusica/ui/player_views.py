"""
Tres vistas del reproductor que muestran lo MISMO con distinto formato:

  * BarraEscritorio     - barra inferior de tres zonas (como Spotify en el PC).
  * MiniReproductor     - tarjeta compacta sobre la barra de navegación (móvil).
  * ReproductorCompleto - pantalla completa que sube al tocar el mini (móvil).

La app mantiene una lista de vistas y las actualiza todas con los mismos métodos
(pista, portada, progreso, tiempo, reproduciendo, aleatorio, cargando), así que la
lógica de reproducción no sabe cuántas hay ni cómo se ven.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from mimusica.core.formatting import formato_tiempo
from mimusica.ui.theme import (
    COLOR_ACENTO, COLOR_FONDO, COLOR_FONDO_SUAVE, COLOR_SUPERFICIE, COLOR_SUPERFICIE_2,
    COLOR_TEXTO, COLOR_TEXTO_SUAVE, COLOR_MINI, relleno,
)


@dataclass
class Acciones:
    """Lo que las vistas pueden pedirle a la app (se pasan al construirlas)."""
    alternar: Callable          # play / pausa            (async, recibe e)
    anterior: Callable          # (async, recibe e)
    siguiente: Callable         # (async, recibe e)
    detener: Callable           # (async, recibe e)
    aleatorio: Callable         # (sync, recibe e)
    arrastre_inicio: Callable[[], None]
    arrastre_mover: Callable[[float], None]   # valor en ms mientras se arrastra
    arrastre_fin: Callable[[float], None]     # valor en ms al soltar
    volumen: Callable[[float], None]
    expandir: Callable          # abre la pantalla completa (sync, recibe e)
    colapsar: Callable          # la cierra (sync, recibe e)


def _centro():
    return ft.Alignment.CENTER if hasattr(ft, "Alignment") else None


class _Portada:
    """Caja cuadrada que muestra la carátula o, si no hay, un icono."""

    def __init__(self, lado: int, radio: int = 8, icono: float = 24):
        self.lado = lado
        self.icono = ft.Icon(ft.Icons.MUSIC_NOTE, color=COLOR_ACENTO, size=icono)
        self.caja = ft.Container(
            width=lado, height=lado, border_radius=radio, bgcolor=COLOR_SUPERFICIE_2,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS, alignment=_centro(), content=self.icono)

    def poner(self, datos: bytes | None):
        self.caja.content = (
            ft.Image(src=datos, width=self.lado, height=self.lado, fit=ft.BoxFit.COVER)
            if datos else self.icono
        )
        self._ultima = datos

    def redimensionar(self, lado: int):
        self.lado = lado
        self.caja.width = self.caja.height = lado
        if isinstance(self.caja.content, ft.Image):
            self.caja.content.width = self.caja.content.height = lado


def _boton(icono, tooltip, al_pulsar, tam=24, color=COLOR_TEXTO):
    return ft.IconButton(icon=icono, icon_size=tam, icon_color=color, tooltip=tooltip, on_click=al_pulsar)


def _barra_tiempo(acc: Acciones):
    """Slider de posición (ms) + etiquetas de tiempo. Devuelve (slider, t_actual, t_total)."""
    t_actual = ft.Text("0:00", size=12, color=COLOR_TEXTO_SUAVE)
    t_total = ft.Text("0:00", size=12, color=COLOR_TEXTO_SUAVE)
    slider = ft.Slider(
        min=0, max=1000, value=0, expand=True, active_color=COLOR_ACENTO,
        on_change_start=lambda e: acc.arrastre_inicio(),
        on_change=lambda e: acc.arrastre_mover(float(e.control.value)),
        on_change_end=lambda e: acc.arrastre_fin(float(e.control.value)),
    )
    return slider, t_actual, t_total


class _ConBarra:
    """Comportamiento común de las vistas que tienen slider de progreso."""
    slider: ft.Slider
    t_actual: ft.Text
    t_total: ft.Text

    def progreso(self, ms: int, max_ms: int):
        self.slider.max = max(max_ms, 1000)
        self.slider.value = min(max(ms, 0), self.slider.max)
        self.t_actual.value = formato_tiempo(ms / 1000)

    def tiempo(self, ms: int):
        self.t_actual.value = formato_tiempo(ms / 1000)

    def _nueva_duracion(self, duracion_s: float):
        self.slider.max = max(int(duracion_s * 1000), 1000)
        self.slider.value = 0
        self.t_actual.value = "0:00"
        self.t_total.value = formato_tiempo(duracion_s)


# ==========================================================================
# Escritorio: tres zonas (pista | controles + progreso | volumen)
# ==========================================================================
class BarraEscritorio(_ConBarra):
    def __init__(self, acc: Acciones):
        self._portada = _Portada(52, 3)
        self.titulo = ft.Text("Nada en reproducción", weight=ft.FontWeight.BOLD, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS)
        self.artista = ft.Text("Elige una canción de la biblioteca", size=12, color=COLOR_TEXTO_SUAVE,
                               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.slider, self.t_actual, self.t_total = _barra_tiempo(acc)
        self.boton_alea = _boton(ft.Icons.SHUFFLE, "Aleatorio: desactivado", acc.aleatorio, 22, COLOR_TEXTO_SUAVE)
        self.boton_play = _boton(ft.Icons.PLAY_CIRCLE_FILLED, "Reproducir / Pausar", acc.alternar, 44, COLOR_ACENTO)
        self.icono_vol = ft.Icon(ft.Icons.VOLUME_UP, color=COLOR_TEXTO_SUAVE)
        self.slider_vol = ft.Slider(min=0, max=1, value=1, width=130, active_color=COLOR_ACENTO,
                                    on_change=lambda e: acc.volumen(float(e.control.value)))

        izquierda = ft.Row([self._portada.caja,
                            ft.Column([self.titulo, self.artista], spacing=0, expand=True)],
                           spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        centro = ft.Column(
            spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row([self.boton_alea,
                        _boton(ft.Icons.SKIP_PREVIOUS, "Anterior", acc.anterior, 26),
                        self.boton_play,
                        _boton(ft.Icons.SKIP_NEXT, "Siguiente", acc.siguiente, 26),
                        _boton(ft.Icons.STOP_CIRCLE_OUTLINED, "Detener", acc.detener, 22)],
                       alignment=ft.MainAxisAlignment.CENTER, spacing=0),
                ft.Row([self.t_actual, self.slider, self.t_total],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
        )
        derecha = ft.Row([self.icono_vol, self.slider_vol], alignment=ft.MainAxisAlignment.END, spacing=0)
        self.contenedor = ft.Container(
            bgcolor=COLOR_FONDO, padding=relleno(16, 8),
            content=ft.Row([ft.Container(izquierda, expand=3), ft.Container(centro, expand=4),
                            ft.Container(derecha, expand=3)],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=12))

    # ---- interfaz común -------------------------------------------------------
    def pista(self, titulo: str, artista: str, duracion_s: float):
        self.titulo.value, self.artista.value = titulo, artista
        self._portada.poner(None)
        self._nueva_duracion(duracion_s)

    def portada(self, datos): self._portada.poner(datos)

    def reproduciendo(self, activo: bool):
        self.boton_play.icon = ft.Icons.PAUSE_CIRCLE_FILLED if activo else ft.Icons.PLAY_CIRCLE_FILLED
        self.boton_play.tooltip = "Pausar" if activo else "Reproducir"

    def aleatorio(self, activo: bool):
        self.boton_alea.icon_color = COLOR_ACENTO if activo else COLOR_TEXTO_SUAVE
        self.boton_alea.tooltip = "Aleatorio: activado" if activo else "Aleatorio: desactivado"

    def cargando(self, activo: bool): pass

    def volumen_icono(self, v: float):
        self.icono_vol.name = (ft.Icons.VOLUME_OFF if v == 0
                               else ft.Icons.VOLUME_DOWN if v < 0.5 else ft.Icons.VOLUME_UP)


# ==========================================================================
# Móvil: mini-reproductor (tarjeta compacta, toca para expandir)
# ==========================================================================
class MiniReproductor:
    def __init__(self, acc: Acciones):
        self._portada = _Portada(44, 5, 20)
        self.titulo = ft.Text("", size=13, weight=ft.FontWeight.W_500, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS)
        self.artista = ft.Text("", size=11, color=COLOR_TEXTO_SUAVE, max_lines=1,
                               overflow=ft.TextOverflow.ELLIPSIS)
        self.boton_play = _boton(ft.Icons.PLAY_ARROW, "Reproducir / Pausar", acc.alternar, 30)
        self.barra = ft.ProgressBar(value=0, color=COLOR_TEXTO, bgcolor="#414752", bar_height=2)
        self.contenedor = ft.Container(
            visible=False, bgcolor=COLOR_MINI, border_radius=10,
            margin=ft.Margin.symmetric(horizontal=8, vertical=2),
            padding=ft.Padding(left=8, top=6, right=4, bottom=0) if hasattr(ft, "Padding") else 6,
            ink=True, on_click=acc.expandir,
            content=ft.Column(spacing=2, controls=[
                ft.Row([self._portada.caja,
                        ft.Column([self.titulo, self.artista], spacing=0, expand=True),
                        self.boton_play,
                        _boton(ft.Icons.SKIP_NEXT, "Siguiente", acc.siguiente, 24)],
                       spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.barra,
            ]))
        self._max_ms = 1000

    def pista(self, titulo: str, artista: str, duracion_s: float):
        self.titulo.value, self.artista.value = titulo, artista
        self._portada.poner(None)
        self._max_ms = max(int(duracion_s * 1000), 1000)
        self.barra.value = 0

    def portada(self, datos): self._portada.poner(datos)

    def progreso(self, ms: int, max_ms: int):
        self._max_ms = max(max_ms, 1000)
        self.barra.value = min(max(ms / self._max_ms, 0), 1)

    def tiempo(self, ms: int): pass

    def reproduciendo(self, activo: bool):
        self.boton_play.icon = ft.Icons.PAUSE if activo else ft.Icons.PLAY_ARROW
        self.boton_play.tooltip = "Pausar" if activo else "Reproducir"

    def aleatorio(self, activo: bool): pass

    def cargando(self, activo: bool):
        """Mientras el motor carga la pista, la barrita fina se anima (indeterminada)."""
        if activo:
            self.barra.value = None


# ==========================================================================
# Móvil: pantalla completa "Reproduciendo"
# ==========================================================================
class ReproductorCompleto(_ConBarra):
    def __init__(self, acc: Acciones):
        self._portada = _Portada(280, 4, 80)
        self.titulo = ft.Text("Nada en reproducción", size=22, weight=ft.FontWeight.BOLD,
                              text_align=ft.TextAlign.LEFT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
        self.artista = ft.Text("", size=15, color=COLOR_TEXTO_SUAVE, text_align=ft.TextAlign.LEFT,
                               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.slider, self.t_actual, self.t_total = _barra_tiempo(acc)
        self.boton_alea = _boton(ft.Icons.SHUFFLE, "Aleatorio: desactivado", acc.aleatorio, 26, COLOR_TEXTO_SUAVE)
        self.boton_play = _boton(ft.Icons.PLAY_CIRCLE_FILLED, "Reproducir / Pausar", acc.alternar, 72, COLOR_ACENTO)
        self.anillo = ft.ProgressRing(width=18, height=18, stroke_width=2, color=COLOR_ACENTO, visible=False)

        degradado = None
        try:
            degradado = ft.LinearGradient(begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                                          colors=[COLOR_FONDO_SUAVE, COLOR_FONDO])
        except Exception:
            pass
        cuerpo = ft.Column(
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row([_boton(ft.Icons.KEYBOARD_ARROW_DOWN, "Cerrar", acc.colapsar, 32),
                        ft.Text("Reproduciendo", size=14, weight=ft.FontWeight.W_600,
                                color=COLOR_TEXTO_SUAVE, expand=True, text_align=ft.TextAlign.CENTER),
                        ft.Container(width=48)],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=6),
                self._portada.caja,
                ft.Container(height=10),
                ft.Container(ft.Column([self.titulo, self.artista], spacing=2,
                                       horizontal_alignment=ft.CrossAxisAlignment.START),
                             padding=relleno(24, 0)),
                ft.Container(ft.Row([self.t_actual, self.slider, self.t_total],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                             padding=relleno(16, 0)),
                ft.Row([self.boton_alea,
                        _boton(ft.Icons.SKIP_PREVIOUS, "Anterior", acc.anterior, 38),
                        self.boton_play,
                        _boton(ft.Icons.SKIP_NEXT, "Siguiente", acc.siguiente, 38),
                        _boton(ft.Icons.STOP_CIRCLE_OUTLINED, "Detener", acc.detener, 26)],
                       alignment=ft.MainAxisAlignment.CENTER, spacing=2),
                self.anillo,
            ],
        )
        self.contenedor = ft.Container(
            left=0, top=0, right=0, bottom=0,
            bgcolor=COLOR_FONDO, gradient=degradado, padding=relleno(8, 8),
            offset=ft.Offset(0, 1),                        # fuera de pantalla (abajo)
            animate_offset=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
            content=cuerpo)

    def abrir(self): self.contenedor.offset = ft.Offset(0, 0)
    def cerrar(self): self.contenedor.offset = ft.Offset(0, 1)

    def ajustar(self, ancho: float, alto: float):
        """La carátula se adapta al espacio disponible (vertical u horizontal)."""
        lado = int(max(140, min(ancho - 64, alto * 0.36, 420)))
        self._portada.redimensionar(lado)

    def pista(self, titulo: str, artista: str, duracion_s: float):
        self.titulo.value, self.artista.value = titulo, artista
        self._portada.poner(None)
        self._nueva_duracion(duracion_s)

    def portada(self, datos): self._portada.poner(datos)

    def reproduciendo(self, activo: bool):
        self.boton_play.icon = ft.Icons.PAUSE_CIRCLE_FILLED if activo else ft.Icons.PLAY_CIRCLE_FILLED
        self.boton_play.tooltip = "Pausar" if activo else "Reproducir"

    def aleatorio(self, activo: bool):
        self.boton_alea.icon_color = COLOR_ACENTO if activo else COLOR_TEXTO_SUAVE
        self.boton_alea.tooltip = "Aleatorio: activado" if activo else "Aleatorio: desactivado"

    def cargando(self, activo: bool):
        self.anillo.visible = activo
