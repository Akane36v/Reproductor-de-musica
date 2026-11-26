"""
Descargador para Android: yt-dlp SIN FFmpeg.

Android no trae FFmpeg, así que no se convierte a MP3: se baja el audio AAC nativo
de YouTube (M4A), sin recodificar, y las etiquetas y la portada se escriben con mutagen.
"""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

import yt_dlp
from mutagen.mp4 import MP4, MP4Cover
from yt_dlp.utils import DownloadCancelled, DownloadError

from mimusica.adapters.spotify import PLANTILLA_SPOTIFY, descargar_enlace
from mimusica.core.errors import mensaje_error_amigable
from mimusica.core.urls import es_mix_automatico, recurso_spotify


class _RegistroYDL:
    """Logger de yt-dlp: guarda los errores (con ignoreerrors no se lanzan excepciones)."""

    def __init__(self):
        self.errores: list[str] = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errores.append(str(msg))


def _descargar_portada(info: dict) -> bytes | None:
    """Descarga la mejor miniatura JPG (mutagen solo incrusta JPG/PNG; sin FFmpeg no hay conversión)."""
    candidatas = [
        t for t in (info.get("thumbnails") or [])
        if str(t.get("url", "")).split("?")[0].lower().endswith(".jpg")
    ]
    candidatas.sort(key=lambda t: (t.get("preference") or 0, t.get("height") or 0), reverse=True)
    urls = [t["url"] for t in candidatas]
    miniatura = info.get("thumbnail")
    if miniatura and str(miniatura).split("?")[0].lower().endswith(".jpg"):
        urls.append(miniatura)
    for url in urls[:3]:
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                datos = r.read(3_000_000)
            if datos[:2] == b"\xff\xd8":  # firma JPEG
                return datos
        except Exception:
            continue
    return None


def etiquetar_m4a(ruta: str, info: dict) -> None:
    """Escribe título, artista, álbum y portada en un M4A."""
    audio = MP4(ruta)
    titulo = info.get("track") or info.get("title")
    artista = (
        info.get("artist")
        or ", ".join(info.get("artists") or [])
        or info.get("creator")
        or info.get("uploader")
    )
    album = info.get("album") or info.get("playlist_title")
    if titulo:
        audio["\xa9nam"] = [titulo]
    if artista:
        audio["\xa9ART"] = [artista]
    if album:
        audio["\xa9alb"] = [album]
    portada = _descargar_portada(info)
    if portada:
        audio["covr"] = [MP4Cover(portada, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


class DescargadorYtDlpAndroid:
    """Misma interfaz que el de Windows (puerto Descargador); se comunica por callbacks."""

    def __init__(self, on_estado, on_progreso, on_fin, on_error):
        self._on_estado = on_estado
        self._on_progreso = on_progreso
        self._on_fin = on_fin
        self._on_error = on_error
        self._cancelar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._inicio = threading.Lock()

    def problema_de_entorno(self) -> str | None:
        return None  # no se necesita FFmpeg

    @property
    def ocupado(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self, url: str, destino: Path):
        with self._inicio:
            if self.ocupado:
                return
            self._cancelar.clear()
            self._hilo = threading.Thread(target=self._ejecutar, args=(url, destino), daemon=True)
            try:
                self._hilo.start()
            except Exception:
                self._hilo = None
                raise

    def _ejecutar(self, url, destino):
        try:
            self._trabajo(url, destino)
        except DownloadCancelled:
            self._on_fin(0, [], True)
        except Exception as ex:
            self._on_error(mensaje_error_amigable(ex))

    def cancelar(self):
        self._cancelar.set()

    def _trabajo(self, url: str, destino: Path):
        registro = _RegistroYDL()
        contador = {"ok": 0, "ultimo_pct": -1}
        infos: dict[str, dict] = {}
        ultima_info: dict = {}

        def hook_progreso(d):
            nonlocal ultima_info
            if self._cancelar.is_set():
                raise DownloadCancelled("Cancelado por el usuario")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if not total:
                    return
                pct = int(d.get("downloaded_bytes", 0) * 100 / total)
                if pct == contador["ultimo_pct"]:
                    return
                contador["ultimo_pct"] = pct
                info = d.get("info_dict") or {}
                indice = info.get("playlist_index")
                cantidad = info.get("playlist_count") or info.get("n_entries")
                prefijo = f" (pista {indice} de {cantidad})" if indice and cantidad else ""
                self._on_progreso(pct / 100)
                self._on_estado(f"Descargando: {pct}%{prefijo}")
            elif d["status"] == "finished":
                contador["ultimo_pct"] = -1
                ultima_info = d.get("info_dict") or {}
                infos[d.get("filename", "")] = ultima_info
                self._on_progreso(None)
                self._on_estado("Guardando etiquetas y portada...")

        def post_hook(ruta: str):
            """yt-dlp lo llama con la ruta final de cada archivo ya descargado."""
            try:
                etiquetar_m4a(ruta, infos.get(ruta) or ultima_info)
            except Exception:
                pass  # sin etiquetas el archivo sigue siendo válido y reproducible
            contador["ok"] += 1

        opciones = {
            # M4A (AAC) nativo: no requiere FFmpeg. Sin respaldo a otros formatos
            # para que el archivo siempre sea etiquetable y reproducible.
            "format": "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]",
            "outtmpl": str(destino / (PLANTILLA_SPOTIFY if recurso_spotify(url) else "%(title)s.%(ext)s")),
            "windowsfilenames": True,
            "trim_file_name": 150,
            "noplaylist": bool(recurso_spotify(url)) or es_mix_automatico(url),
            "ignoreerrors": "only_download",
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 20,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": registro,
            "progress_hooks": [hook_progreso],
            "post_hooks": [post_hook],
            # Punto de ajuste si YouTube exige un runtime de JavaScript que Android no tiene:
            # "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
        }

        try:
            with yt_dlp.YoutubeDL(opciones) as ydl:
                descargar_enlace(ydl, url, self._cancelar, self._on_estado,
                                 self._on_progreso, registro.errores)
        except DownloadCancelled:
            self._on_fin(contador["ok"], [], True)
            return
        except DownloadError as e:
            self._on_error(mensaje_error_amigable(e))
            return
        except Exception as e:  # nunca cerrar la app por un fallo inesperado
            self._on_error(mensaje_error_amigable(e))
            return

        if self._cancelar.is_set():
            self._on_fin(contador["ok"], [], True)
        elif contador["ok"] == 0 and registro.errores:
            self._on_error(mensaje_error_amigable(registro.errores[0]))
        else:
            self._on_fin(contador["ok"], registro.errores, False)
