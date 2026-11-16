"""Enlaces públicos de Spotify → metadatos → coincidencias de audio en YouTube.

No usa sesiones de Spotify ni descarga sus avances de audio. La vista pública
puede recortar playlists largas; se rechaza una lista posiblemente incompleta.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from threading import Event

import yt_dlp
from yt_dlp.networking import Request
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import DownloadCancelled, DownloadError

from mimusica.core.urls import recurso_spotify

PLANTILLA_SPOTIFY = "%(artist).40s - %(track).65s [%(spotify_id)s].%(ext)s"
LIMITE_VISTA_PUBLICA = 100


class ErrorSpotify(ValueError):
    def __str__(self):
        return "Spotify: " + super().__str__()


@dataclass(frozen=True)
class PistaSpotify:
    id: str
    titulo: str
    artista: str
    duracion: float


@dataclass(frozen=True)
class ColeccionSpotify:
    nombre: str
    pistas: tuple[PistaSpotify, ...]
    omitidas: int = 0


class _DatosPagina(HTMLParser):
    def __init__(self):
        super().__init__()
        self.leyendo = False
        self.fragmentos: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.leyendo = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.leyendo = False

    def handle_data(self, data):
        if self.leyendo:
            self.fragmentos.append(data)


def interpretar_spotify(html: str, tipo: str, id_: str) -> ColeccionSpotify:
    """Lee únicamente la entidad solicitada, nunca recomendaciones de la página."""
    parser = _DatosPagina()
    parser.feed(html)
    try:
        datos = json.loads("".join(parser.fragmentos))
        entidad = datos["props"]["pageProps"]["state"]["data"]["entity"]
        if entidad.get("type") != tipo or entidad.get("id") != id_:
            raise ValueError("Entidad distinta")
    except (ValueError, KeyError, TypeError, AttributeError) as ex:
        raise ErrorSpotify("No se pudo leer este enlace. Comprueba que sea una canción o playlist pública. "
                           "Las playlists privadas no están disponibles.") from ex
    entradas = [entidad] if tipo == "track" else entidad.get("trackList")
    if not isinstance(entradas, list) or not entradas:
        raise ErrorSpotify("La playlist está vacía o Spotify no permite leer sus canciones.")
    total = entidad.get("totalTracks") or entidad.get("trackCount")
    if tipo == "playlist" and (len(entradas) >= LIMITE_VISTA_PUBLICA
                               or isinstance(total, int) and total > len(entradas)):
        raise ErrorSpotify("La vista pública puede recortar esta playlist. Para descargarla completa, "
                           "divídela en playlists públicas de menos de 100 canciones y pega cada enlace.")
    pistas = []
    omitidas = 0
    for entrada in entradas:
        if not isinstance(entrada, dict):
            omitidas += 1
            continue
        uri_cruda = entrada.get("uri")
        uri = recurso_spotify(uri_cruda) if isinstance(uri_cruda, str) else None
        artistas = entrada.get("artists") or []
        artista = ", ".join(a.get("name", "") for a in artistas if isinstance(a, dict))
        artista = artista or entrada.get("subtitle", "")
        titulo = entrada.get("title") or entrada.get("name") or ""
        duracion = entrada.get("duration")
        if (not uri or uri[0] != "track" or not isinstance(titulo, str)
                or not isinstance(artista, str) or not titulo.strip() or not artista.strip()
                or not isinstance(duracion, (float, int)) or duracion <= 0):
            omitidas += 1
            continue
        pistas.append(PistaSpotify(uri[1], titulo.strip(), artista.strip(), duracion / 1000))
    if not pistas:
        raise ErrorSpotify("No se encontraron canciones disponibles en este enlace.")
    return ColeccionSpotify(str(entidad.get("title") or entidad.get("name") or "Spotify"),
                            tuple(pistas), omitidas)


def _comprobar_cancelacion(cancelar: Event):
    if cancelar.is_set():
        raise DownloadCancelled("Cancelado por el usuario")


def leer_spotify(url: str, cliente, cancelar: Event) -> ColeccionSpotify:
    recurso = recurso_spotify(url)
    if not recurso:
        raise ErrorSpotify("Usa el enlace de una canción o playlist en open.spotify.com.")
    _comprobar_cancelacion(cancelar)
    try:
        solicitud = Request(f"https://open.spotify.com/embed/{recurso[0]}/{recurso[1]}",
                            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es,en;q=0.8"})
        with cliente.urlopen(solicitud) as respuesta:
            datos = respuesta.read(4_000_001)
        _comprobar_cancelacion(cancelar)
        if len(datos) > 4_000_000:
            raise ErrorSpotify("La playlist es demasiado grande para leerla. Divídela en listas más pequeñas.")
        return interpretar_spotify(datos.decode("utf-8"), *recurso)
    except (DownloadCancelled, ErrorSpotify):
        raise
    except Exception as ex:
        _comprobar_cancelacion(cancelar)
        raise ErrorSpotify("No se pudo consultar la página pública. Revisa la conexión y vuelve a intentarlo. "
                           "Si persiste, Spotify podría estar limitando el acceso.") from ex


def _palabras(texto: str) -> set[str]:
    normal = unicodedata.normalize("NFKD", texto.casefold())
    normal = "".join(c for c in normal if not unicodedata.combining(c))
    return set(re.findall(r"[^\W_]+", normal))


def elegir_coincidencia(pista: PistaSpotify, candidatas: list[dict]) -> str | None:
    """Exige título, artista y duración compatibles; evita versiones no solicitadas."""
    titulo = _palabras(pista.titulo)
    artista = _palabras(pista.artista.split(",")[0])
    versiones = {"cover", "karaoke", "instrumental", "remix", "live", "acoustic",
                 "slowed", "sped", "nightcore", "tribute", "reaction", "tutorial"}
    mejor: tuple[float, str] | None = None
    for candidata in candidatas:
        if not isinstance(candidata, dict):
            continue
        id_ = candidata.get("id", "")
        if not isinstance(id_, str) or not re.fullmatch(r"[\w-]{11}", id_, re.ASCII):
            continue
        duracion = candidata.get("duration")
        if (candidata.get("is_live") or not isinstance(duracion, (float, int))
                or abs(duracion - pista.duracion) > max(12, pista.duracion * 0.08)):
            continue
        nombre = _palabras(candidata.get("title") or "")
        canal = _palabras(candidata.get("channel") or candidata.get("uploader") or "")
        if (nombre & versiones) - (titulo | artista):
            continue
        acierto_titulo = len(titulo & nombre) / max(len(titulo), 1)
        acierto_artista = len(artista & (nombre | canal)) / max(len(artista), 1)
        if acierto_titulo < 0.8 or acierto_artista < 0.8:
            continue
        puntuacion = (acierto_titulo * 6 + acierto_artista * 4
                      + 2 * (1 - abs(duracion - pista.duracion) / max(pista.duracion, 1))
                      + (1.2 if artista and artista <= canal else 0)
                      + (0.5 if "topic" in canal else 0)
                      + (0.3 if "audio" in nombre else 0))
        if mejor is None or puntuacion > mejor[0]:
            mejor = (puntuacion, f"https://www.youtube.com/watch?v={id_}")
    return mejor[1] if mejor else None


class _EtiquetasSpotify(PostProcessor):
    """Añade metadatos antes de calcular el nombre y de escribir etiquetas."""
    def __init__(self, ydl):
        super().__init__(ydl)
        self.pista: PistaSpotify | None = None
        self.indice = 0
        self.total = 0

    def run(self, info):
        if self.pista:
            info.update(track=self.pista.titulo, artist=self.pista.artista,
                        artists=[self.pista.artista], spotify_id=self.pista.id,
                        playlist_index=self.indice, playlist_count=self.total)
        return [], info


def descargar_enlace(ydl, url: str, cancelar: Event, on_estado, on_progreso, errores: list[str]):
    """Mantiene la descarga habitual y resuelve Spotify pista por pista."""
    if not recurso_spotify(url):
        return ydl.download([url])
    opciones = {"quiet": True, "no_warnings": True, "skip_download": True,
                "extract_flat": "in_playlist", "socket_timeout": 20, "retries": 2,
                "logger": ydl.params.get("logger")}
    on_estado("Leyendo canciones de Spotify...")
    on_progreso(None)
    with yt_dlp.YoutubeDL(opciones) as buscador:
        coleccion = leer_spotify(url, buscador, cancelar)
        if coleccion.omitidas:
            errores.append(f"Spotify: {coleccion.omitidas} elementos sin datos de canción se omitieron.")
        etiquetas = _EtiquetasSpotify(ydl)
        etiquetas.total = len(coleccion.pistas)
        ydl.add_post_processor(etiquetas, when="pre_process")
        for indice, pista in enumerate(coleccion.pistas, 1):
            _comprobar_cancelacion(cancelar)
            etiquetas.pista, etiquetas.indice = pista, indice
            on_progreso(None)
            on_estado(f"Buscando {indice} de {etiquetas.total}: {pista.titulo} · {pista.artista}")
            try:
                resultado = buscador.extract_info(f"ytsearch5:{pista.artista} {pista.titulo} audio", download=False)
                _comprobar_cancelacion(cancelar)
                candidatas = list((resultado or {}).get("entries") or [])
                coincidencia = elegir_coincidencia(pista, candidatas)
                if not coincidencia:
                    errores.append(f"Spotify: no se encontró una versión compatible de «{pista.titulo}» ({pista.artista}).")
                    continue
                on_estado(f"Descargando {indice} de {etiquetas.total}: {pista.titulo}")
                _comprobar_cancelacion(cancelar)
                ydl.download([coincidencia])
            except DownloadCancelled:
                raise
            except DownloadError:
                errores.append(f"Spotify: no se pudo buscar o descargar «{pista.titulo}» ({pista.artista}).")
        _comprobar_cancelacion(cancelar)
