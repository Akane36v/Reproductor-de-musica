"""Ensamblado de los adaptadores de Android."""

from mimusica.adapters.android.downloader import DescargadorYtDlpAndroid
from mimusica.adapters.android.media_controls import ControlesMultimediaAndroid
from mimusica.adapters.android.player import ReproductorFlet
from mimusica.adapters.android.storage import carpeta_datos, carpeta_musica
from mimusica.core.ports import Plataforma


def crear_plataforma() -> Plataforma:
    return Plataforma(
        nombre="android",
        permite_elegir_carpeta=False,      # se guarda en el almacenamiento privado de la app
        carpeta_descargas=carpeta_musica,
        carpeta_datos=carpeta_datos,
        crear_descargador=DescargadorYtDlpAndroid,
        crear_reproductor=ReproductorFlet,  # recibe la página de Flet
        crear_controles_multimedia=ControlesMultimediaAndroid,  # notificación y segundo plano
        extensiones=(".m4a",),
    )
