"""Descargador para Windows: yt-dlp + FFmpeg -> MP3 192 kbps con etiquetas y portada."""

from __future__ import annotations

import threading
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from mimusica.adapters.windows.tools import localize_ffmpeg
from mimusica.adapters.spotify import PLANTILLA_SPOTIFY, descargar_enlace
from mimusica.core.errors import mensaje_error_amigable
from mimusica.core.urls import es_mix_automatico, recurso_spotify


class _RegistroYDL:
    """Logger de yt-dlp: guarda los errores (con ignoreerrors yt-dlp no lanza excepciones)."""

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


class DescargadorYtDlp:
    """
    Ejecuta yt-dlp + FFmpeg en un hilo secundario. No conoce Flet: se comunica
    únicamente mediante callbacks (la interfaz los envuelve para actualizarse
    de forma segura desde otro hilo).
    """

    def __init__(self, on_estado, on_progreso, on_fin, on_error):
        self._on_estado = on_estado      # (texto: str)
        self._on_progreso = on_progreso  # (valor: float | None)  0..1, None = indeterminado
        self._on_fin = on_fin            # (descargados: int, errores: list[str], cancelado: bool)
        self._on_error = on_error        # (mensaje: str)
        self._cancelar = threading.Event()
        self._hilo: threading.Thread | None = None
        self.carpeta_ffmpeg: str | None = None

    def problema_de_entorno(self) -> str | None:
        """Vuelve a buscar FFmpeg (por si lo copiaron después de abrir la app)."""
        self.carpeta_ffmpeg = localize_ffmpeg()
        if self.carpeta_ffmpeg is None:
            return ("No se encontraron ffmpeg.exe y ffprobe.exe. Colócalos en la carpeta "
                    "tools/ del proyecto para poder convertir a MP3.")
        return None

    @property
    def ocupado(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self, url: str, destino: Path):
        if self.ocupado:
            return
        self._cancelar.clear()
        self._hilo = threading.Thread(target=self._trabajo, args=(url, destino), daemon=True)
        self._hilo.start()

    def cancelar(self):
        self._cancelar.set()

    def _trabajo(self, url: str, destino: Path):
        registro = _RegistroYDL()
        contador = {"ok": 0, "ultimo_pct": -1}

        def hook_progreso(d):
            # Se ejecuta en el hilo de descarga; aquí se atiende la cancelación.
            if self._cancelar.is_set():
                raise DownloadCancelled("Cancelado por el usuario")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if not total:
                    return
                pct = int(d.get("downloaded_bytes", 0) * 100 / total)
                if pct == contador["ultimo_pct"]:
                    return  # evita saturar la interfaz con actualizaciones repetidas
                contador["ultimo_pct"] = pct
                info = d.get("info_dict") or {}
                indice = info.get("playlist_index")
                cantidad = info.get("playlist_count") or info.get("n_entries")
                prefijo = f" (pista {indice} de {cantidad})" if indice and cantidad else ""
                self._on_progreso(pct / 100)
                self._on_estado(f"Descargando: {pct}%{prefijo}")
            elif d["status"] == "finished":
                contador["ultimo_pct"] = -1

        def hook_postproceso(d):
            nombre = d.get("postprocessor", "")
            if nombre == "ExtractAudio":
                if d["status"] == "started":
                    self._on_progreso(None)
                    self._on_estado("Convirtiendo a MP3...")
                elif d["status"] == "finished":
                    contador["ok"] += 1
            elif d["status"] == "started" and nombre in ("Metadata", "EmbedThumbnail"):
                self._on_estado("Escribiendo etiquetas y portada...")

        opciones = {
            "format": "bestaudio/best",
            "outtmpl": str(destino / (PLANTILLA_SPOTIFY if recurso_spotify(url) else "%(title)s.%(ext)s")),
            # Elimina de los nombres los caracteres prohibidos \ / : * ? " < > |
            "windowsfilenames": True,
            "trim_file_name": 150,
            # Un 'Mix' automático con video suelto no se trata como lista
            "noplaylist": bool(recurso_spotify(url)) or es_mix_automatico(url),
            # En listas/álbumes, un elemento fallido no detiene el resto
            "ignoreerrors": "only_download",
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 20,
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": registro,
            "progress_hooks": [hook_progreso],
            "postprocessor_hooks": [hook_postproceso],
            "postprocessors": [
                # 1) Audio -> MP3 a 192 kbps
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                # 2) La portada se convierte a JPG antes de incrustarla
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                # 3) Título, artista, álbum, pista... -> etiquetas ID3
                {"key": "FFmpegMetadata", "add_metadata": True},
                # 4) Incrusta la portada en el MP3
                {"key": "EmbedThumbnail"},
            ],
            # Recorta la portada a cuadrado (las miniaturas de YouTube son 16:9)
            "postprocessor_args": {
                "thumbnailsconvertor+ffmpeg_o": [
                    "-c:v", "mjpeg", "-vf",
                    "crop='if(gt(ih,iw),iw,ih)':'if(gt(iw,ih),ih,iw)'",
                ]
            },
        }
        # FFmpeg portátil: se inyecta la ruta, no hace falta tocar el PATH
        if self.carpeta_ffmpeg:
            opciones["ffmpeg_location"] = self.carpeta_ffmpeg

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
        except Exception as e:  # cualquier fallo inesperado: nunca cerrar la app
            self._on_error(mensaje_error_amigable(e))
            return

        if self._cancelar.is_set():
            self._on_fin(contador["ok"], [], True)
        elif contador["ok"] == 0 and registro.errores:
            self._on_error(mensaje_error_amigable(registro.errores[0]))
        else:
            self._on_fin(contador["ok"], registro.errores, False)
