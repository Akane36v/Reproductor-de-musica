"""Reproductor para Windows basado en pygame.mixer."""

from __future__ import annotations

import os

# pygame solo se usa para reproducir audio (independiente del cliente de Flet)
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
except ImportError:  # el error se muestra en pantalla al iniciar
    pygame = None


class ReproductorPygame:
    """
    Motor de reproducción sobre pygame.mixer (MP3 local). No conoce Flet.
    pygame.get_pos() solo cuenta desde el último play(), por eso se guarda el
    desplazamiento (_inicio_ms) para poder saltar a cualquier punto de la pista.
    """

    def __init__(self):
        if pygame is None:
            raise RuntimeError("Falta instalar pygame: pip install pygame")
        pygame.mixer.init()
        self.volumen = 1.0
        self._ruta: str | None = None
        self._inicio_ms = 0
        self._pausado = False
        self._activo = False

    @property
    def activo(self) -> bool:
        return self._activo

    def reproducir(self, ruta: str, inicio_ms: int = 0):
        pygame.mixer.music.load(ruta)
        pygame.mixer.music.set_volume(self.volumen)
        pygame.mixer.music.play(start=inicio_ms / 1000)
        self._ruta, self._inicio_ms = ruta, inicio_ms
        self._pausado, self._activo = False, True

    def pausar(self):
        if self._activo and not self._pausado:
            pygame.mixer.music.pause()
            self._pausado = True

    def reanudar(self):
        if self._activo and self._pausado:
            pygame.mixer.music.unpause()
            self._pausado = False

    def detener(self):
        pygame.mixer.music.stop()
        self._pausado, self._activo = False, False

    def liberar(self):
        """Suelta el archivo actual (Windows no deja borrar un archivo abierto)."""
        pygame.mixer.music.stop()
        if hasattr(pygame.mixer.music, "unload"):
            pygame.mixer.music.unload()
        self._pausado, self._activo = False, False

    def saltar(self, ms: int):
        if self._ruta and self._activo:
            estaba_en_pausa = self._pausado
            self.reproducir(self._ruta, ms)
            if estaba_en_pausa:
                self.pausar()

    def posicion_ms(self) -> int:
        return self._inicio_ms + max(0, pygame.mixer.music.get_pos())

    def terminado(self) -> bool:
        """True cuando la pista llegó sola a su final (no por pausa ni por Stop)."""
        return self._activo and not self._pausado and not pygame.mixer.music.get_busy()

    def poner_volumen(self, valor: float):
        self.volumen = valor
        pygame.mixer.music.set_volume(valor)
