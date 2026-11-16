"""Cola de reproducción con modo aleatorio. Lógica pura, fácil de probar."""

from __future__ import annotations

import random

from mimusica.core.models import Cancion


class ColaReproduccion:
    """
    Mantiene la lista de canciones a reproducir y el orden en que se recorren.

    - Orden normal: el de la lista.
    - Modo aleatorio: se baraja toda la lista UNA vez (sin repetir hasta agotarla); la
      canción actual se queda primera. "Anterior" regresa por lo ya reproducido.
    """

    def __init__(self):
        self._canciones: list[Cancion] = []
        self._orden: list[int] = []      # posiciones de _canciones en el orden de reproducción
        self._pos: int = -1              # posición actual dentro de _orden
        self.aleatorio: bool = False

    # ---- consulta ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._canciones)

    @property
    def vacia(self) -> bool:
        return not self._canciones

    @property
    def indice(self) -> int:
        """Índice de la canción actual dentro de la lista original (-1 si no hay)."""
        return self._orden[self._pos] if 0 <= self._pos < len(self._orden) else -1

    def actual(self) -> Cancion | None:
        i = self.indice
        return self._canciones[i] if i >= 0 else None

    def hay_siguiente(self) -> bool:
        return self._pos + 1 < len(self._orden)

    # ---- construcción ------------------------------------------------------
    def cargar(self, canciones: list[Cancion], inicio: int = 0) -> None:
        """Reemplaza la cola y se posiciona en 'inicio' (índice de la lista dada)."""
        self._canciones = list(canciones)
        if not self._canciones:
            self._orden, self._pos = [], -1
            return
        inicio = min(max(inicio, 0), len(self._canciones) - 1)
        self._construir_orden(inicio)

    def _construir_orden(self, actual: int) -> None:
        n = len(self._canciones)
        if self.aleatorio:
            resto = [i for i in range(n) if i != actual]
            random.shuffle(resto)
            self._orden, self._pos = [actual] + resto, 0
        else:
            self._orden, self._pos = list(range(n)), actual

    def poner_aleatorio(self, activo: bool) -> None:
        """Activa/desactiva el modo aleatorio sin cambiar la canción que suena."""
        self.aleatorio = activo
        if self._canciones:
            actual = self.indice if self.indice >= 0 else 0
            self._construir_orden(actual)

    def quitar(self, ruta: str) -> bool:
        """
        Quita una canción de la cola (p. ej. al borrarla). Devuelve True si era la actual.
        Si era la actual, la siguiente del orden pasa a ocupar su lugar; si no había
        siguiente, la cola queda "después del final" (actual() es None y anterior() vuelve
        a la última canción).
        """
        idx = next((i for i, c in enumerate(self._canciones) if c.ruta == ruta), None)
        if idx is None:
            return False
        era_actual = idx == self.indice
        pos_quitada = self._orden.index(idx)
        del self._canciones[idx]
        self._orden = [i - 1 if i > idx else i for i in self._orden if i != idx]
        if not self._canciones:
            self._orden, self._pos = [], -1
        elif era_actual:
            self._pos = min(pos_quitada, len(self._orden))
        elif pos_quitada < self._pos:
            self._pos -= 1
        return era_actual

    # ---- navegación ----------------------------------------------------------
    def siguiente(self) -> Cancion | None:
        """Avanza y devuelve la nueva canción, o None si se llegó al final."""
        if not self.hay_siguiente():
            return None
        self._pos += 1
        return self.actual()

    def anterior(self) -> Cancion | None:
        """Retrocede (o se queda en la primera) y devuelve la canción."""
        if self._pos > 0:
            self._pos -= 1
        return self.actual()

    def ir_a(self, indice: int) -> Cancion | None:
        """Salta a una canción concreta de la lista (si estaba ya en el orden, sin rebarajar)."""
        if not (0 <= indice < len(self._canciones)):
            return None
        self._pos = self._orden.index(indice)
        return self.actual()
