"""
Registro de diagnóstico en memoria (últimos ~400 eventos).

Sirve para investigar fallos que solo ocurren en el teléfono (p. ej. con la app en segundo
plano): la app lo muestra en el diálogo "Diagnóstico" y se puede copiar y pegar. No guarda
datos personales: solo nombres de eventos, tiempos y títulos de canciones.
"""

from __future__ import annotations

import threading
import time
from collections import deque

_lineas: deque[str] = deque(maxlen=400)
_bloqueo = threading.Lock()


def registrar(origen: str, mensaje: str) -> None:
    ahora = time.time()
    marca = time.strftime("%H:%M:%S", time.localtime(ahora)) + f".{int((ahora % 1) * 1000):03d}"
    with _bloqueo:
        _lineas.append(f"{marca} {origen}: {mensaje}")


def texto(ultimas: int = 150) -> str:
    with _bloqueo:
        lineas = list(_lineas)[-ultimas:]
    return "\n".join(lineas) if lineas else "(sin eventos todavía)"
