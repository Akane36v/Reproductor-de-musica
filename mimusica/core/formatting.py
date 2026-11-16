"""Utilidades de formato."""

from __future__ import annotations


def formato_tiempo(segundos: float | None) -> str:
    """Convierte segundos a 'm:ss' o 'h:mm:ss'."""
    total = int(max(0, segundos or 0))
    horas, resto = divmod(total, 3600)
    minutos, seg = divmod(resto, 60)
    return f"{horas}:{minutos:02d}:{seg:02d}" if horas else f"{minutos}:{seg:02d}"
