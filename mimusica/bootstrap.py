"""
Punto de ensamblado: elige los adaptadores según la plataforma.
Es el ÚNICO lugar que sabe qué implementación va con qué sistema.
"""

from __future__ import annotations

import os
import sys

from mimusica.core.ports import Plataforma


def es_android() -> bool:
    """Detecta Android. Flet define FLET_PLATFORM; el resto son respaldos."""
    return (
        os.environ.get("FLET_PLATFORM", "").lower() == "android"
        or sys.platform == "android"
        or "ANDROID_ARGUMENT" in os.environ
        or "ANDROID_STORAGE" in os.environ
    )


def crear_plataforma() -> Plataforma:
    if es_android():
        from mimusica.adapters.android import crear_plataforma as crear_android
        return crear_android()
    from mimusica.adapters.windows import crear_plataforma as crear_windows
    return crear_windows()
