"""Ensamblado de los adaptadores de Windows."""

from mimusica.adapters.windows.downloader import DescargadorYtDlp
from mimusica.adapters.windows.media_controls import ControlesMultimediaWindows
from mimusica.adapters.windows.player import ReproductorPygame
from mimusica.adapters.windows.storage import carpeta_datos, carpeta_descargas
from mimusica.core.ports import Plataforma


def crear_plataforma() -> Plataforma:
    return Plataforma(
        nombre="windows",
        permite_elegir_carpeta=True,
        carpeta_descargas=carpeta_descargas,
        carpeta_datos=carpeta_datos,
        crear_descargador=DescargadorYtDlp,
        crear_reproductor=lambda page: ReproductorPygame(),
        crear_controles_multimedia=ControlesMultimediaWindows,
    )
