"""Regresiones de importación, selección y descargas Spotify sin conexiones externas."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from mimusica.adapters import spotify
from mimusica.adapters.android import downloader as android
from mimusica.adapters.windows import downloader as windows
from mimusica.core.errors import mensaje_error_amigable
from mimusica.core.urls import validar_url, recurso_spotify

ID = '1Vej0qeQ3ioKwpI6FUbRv1'
LISTA = '3cEYpjA9oz9GiPac4AsH4n'
URL = f'https://open.spotify.com/track/{ID}'
PISTA = spotify.PistaSpotify(ID, 'Papercut', 'Linkin Park', 184.866)


def entidad_pista(**cambios):
    return dict({'type': 'track', 'id': ID, 'uri': f'spotify:track:{ID}',
                 'title': 'Papercut', 'artists': [{'name': 'Linkin Park'}],
                 'duration': 184866}, **cambios)


def html(entidad):
    datos = {'props': {'pageProps': {'state': {'data': {'entity': entidad}}}}}
    return '<script type="application/json" id="__NEXT_DATA__">' + json.dumps(datos) + '</script>'


def candidata(**cambios):
    return dict({'id': '2K-evRnwcSc', 'title': 'Papercut', 'channel': 'Linkin Park',
                 'duration': 187}, **cambios)


class Enlaces(unittest.TestCase):
    def test_normaliza_enlaces_y_uri(self):
        for enlace in (URL + '?si=abc', f'open.spotify.com/intl-es/track/{ID}',
                       f'spotify:track:{ID}', f'https://open.spotify.com/embed/track/{ID}'):
            self.assertEqual(validar_url(enlace), URL)
        self.assertEqual(recurso_spotify(f'https://open.spotify.com/playlist/{LISTA}'), ('playlist', LISTA))

    def test_rechaza_hosts_y_recursos_ajenos(self):
        for enlace in (f'https://open.spotify.com.ejemplo.com/track/{ID}',
                       f'https://usuario@open.spotify.com/track/{ID}',
                       f'https://open.spotify.com/album/{ID}',
                       'https://open.spotify.com/track/corto', 'https://[',
                       f'https://open.spotify.com:invalid/track/{ID}'):
            self.assertIsNone(validar_url(enlace), enlace)

    def test_youtube_se_conserva(self):
        for enlace in ('https://youtu.be/2K-evRnwcSc', 'https://www.youtube.com/watch?v=2K-evRnwcSc',
                       'https://music.youtube.com/playlist?list=PL123'):
            self.assertEqual(validar_url(enlace), enlace)


class Lectura(unittest.TestCase):
    def test_cancion_y_artistas(self):
        coleccion = spotify.interpretar_spotify(html(entidad_pista()), 'track', ID)
        self.assertEqual(coleccion.pistas, (PISTA,))

    def test_playlist_conserva_orden_y_duplicados_y_omite_podcasts(self):
        entrada = {'uri': f'spotify:track:{ID}', 'title': 'Papercut',
                   'subtitle': 'Linkin Park', 'duration': 184866}
        entidad = {'id': LISTA, 'type': 'playlist', 'title': 'Favoritas',
                   'trackList': [entrada, {'uri': 'spotify:episode:' + ID}, entrada]}
        coleccion = spotify.interpretar_spotify(html(entidad), 'playlist', LISTA)
        self.assertEqual(coleccion.pistas, (PISTA, PISTA))
        self.assertEqual(coleccion.omitidas, 1)

    def test_no_descarga_lista_posiblemente_truncada(self):
        for entradas, total in (([entidad_pista()] * 100, None), ([entidad_pista()], 80)):
            entidad = {'id': LISTA, 'type': 'playlist', 'trackList': entradas, 'totalTracks': total}
            with self.assertRaisesRegex(spotify.ErrorSpotify, 'divídela'):
                spotify.interpretar_spotify(html(entidad), 'playlist', LISTA)

    def test_pagina_privada_o_otra_entidad_no_produce_canciones(self):
        for pagina in ('<h1>Page not available</h1>', html(entidad_pista(id=LISTA)), '<script id="__NEXT_DATA__">[]</script>'):
            with self.assertRaises(spotify.ErrorSpotify):
                spotify.interpretar_spotify(pagina, 'track', ID)

    def test_cancelacion_antes_y_despues_de_peticion(self):
        cancelar = Event()
        cliente = Mock()
        cancelar.set()
        with self.assertRaises(DownloadCancelled):
            spotify.leer_spotify(URL, cliente, cancelar)
        cliente.urlopen.assert_not_called()
        cancelar.clear()
        def responder(_):
            cancelar.set()
            return io.BytesIO(html(entidad_pista()).encode())
        cliente.urlopen.side_effect = responder
        with self.assertRaises(DownloadCancelled):
            spotify.leer_spotify(URL, cliente, cancelar)

    def test_error_de_red_amigable(self):
        cliente = Mock()
        cliente.urlopen.side_effect = OSError('sin red')
        with self.assertRaises(spotify.ErrorSpotify) as error:
            spotify.leer_spotify(URL, cliente, Event())
        self.assertIn('Revisa la conexión', mensaje_error_amigable(error.exception))


class Coincidencias(unittest.TestCase):
    def test_prefiere_canal_del_artista(self):
        video = spotify.elegir_coincidencia(PISTA, [
            candidata(id='PkmoIIdZ3ZU', title='Linkin Park - Papercut (Audio)', channel='Otro canal', duration=185),
            candidata(),
        ])
        self.assertEqual(video, 'https://www.youtube.com/watch?v=2K-evRnwcSc')

    def test_rechaza_version_artista_duracion_y_directo_incorrectos(self):
        for cambios in ({'title': 'Linkin Park - Papercut karaoke'}, {'channel': 'Otro artista'},
                        {'duration': 500}, {'title': 'Otra canción'}, {'is_live': True},
                        {'duration': None}, {'id': '../../archivo'}):
            self.assertIsNone(spotify.elegir_coincidencia(PISTA, [candidata(**cambios)]))

    def test_permite_version_solicitada(self):
        pista = spotify.PistaSpotify(ID, 'Papercut - Live', 'Linkin Park', 185)
        self.assertIsNotNone(spotify.elegir_coincidencia(pista, [candidata(title='Papercut Live')]))

    def test_unicode_y_acentos(self):
        pista = spotify.PistaSpotify(ID, 'Canción 라일락', 'Artista', 180)
        self.assertIsNotNone(spotify.elegir_coincidencia(pista, [
            candidata(title='Artista - Cancion 라일락', channel='Artista', duration=180)]))


class Flujo(unittest.TestCase):
    def setUp(self):
        self.ydl = Mock()
        self.ydl.params = {}
        self.ydl._postprocessor_hooks = []
        self.cancelar = Event()
        self.errores = []
        self.buscador = Mock()
        self.buscador.__enter__ = Mock(return_value=self.buscador)
        self.buscador.__exit__ = Mock(return_value=False)
        self.buscador.extract_info.return_value = {'entries': [candidata()]}

    def ejecutar(self, pistas=(PISTA,)):
        with patch.object(spotify.yt_dlp, 'YoutubeDL', return_value=self.buscador), \
             patch.object(spotify, 'leer_spotify', return_value=spotify.ColeccionSpotify('Lista', pistas)):
            spotify.descargar_enlace(self.ydl, URL, self.cancelar, Mock(), Mock(), self.errores)

    def test_descarga_coincidencia_y_añade_etiquetas(self):
        self.ejecutar()
        self.ydl.download.assert_called_once_with(['https://www.youtube.com/watch?v=2K-evRnwcSc'])
        pp = self.ydl.add_post_processor.call_args.args[0]
        _, info = pp.run({'title': 'Título del video'})
        self.assertEqual((info['track'], info['artist'], info['spotify_id']), ('Papercut', 'Linkin Park', ID))
        self.assertEqual((info['playlist_index'], info['playlist_count']), (1, 1))

    def test_fallo_en_pista_no_detiene_el_resto(self):
        self.buscador.extract_info.side_effect = [DownloadError('fallo simulado'), {'entries': [candidata()]}]
        self.ejecutar((PISTA, PISTA))
        self.assertEqual(self.ydl.download.call_count, 1)
        self.assertEqual(len(self.errores), 1)

    def test_no_inventa_coincidencias(self):
        self.buscador.extract_info.return_value = {'entries': []}
        self.ejecutar()
        self.ydl.download.assert_not_called()
        self.assertIn('no se encontró', self.errores[0])

    def test_cancelacion_durante_busqueda_evitar_descarga(self):
        def buscar(*args, **kwargs):
            self.cancelar.set()
            return {'entries': [candidata()]}
        self.buscador.extract_info.side_effect = buscar
        with self.assertRaises(DownloadCancelled):
            self.ejecutar()
        self.ydl.download.assert_not_called()

    def test_youtube_usa_el_flujo_original(self):
        url = 'https://youtu.be/2K-evRnwcSc'
        spotify.descargar_enlace(self.ydl, url, self.cancelar, Mock(), Mock(), self.errores)
        self.ydl.download.assert_called_once_with([url])
        self.ydl.add_post_processor.assert_not_called()

    def test_nombre_unico_sanitizado_con_ydl_real(self):
        with yt_dlp.YoutubeDL({'outtmpl': spotify.PLANTILLA_SPOTIFY, 'windowsfilenames': True}) as ydl:
            pp = spotify._EtiquetasSpotify(ydl)
            pp.pista = spotify.PistaSpotify(ID, 'A/B: ' + 't' * 200, 'Artista', 180)
            ydl.add_post_processor(pp, when='pre_process')
            info, _ = ydl.pre_process({'id': '2K-evRnwcSc', 'title': 'Video', 'ext': 'm4a'})
            archivo = ydl.prepare_filename(info)
            self.assertIn(ID, archivo)
            self.assertLess(len(archivo), 150)
            self.assertNotIn('/', archivo)


class Adaptadores(unittest.TestCase):
    def test_ambas_plataformas_enrutan_spotify_y_reportan_errores(self):
        for modulo, clase in ((android, android.DescargadorYtDlpAndroid), (windows, windows.DescargadorYtDlp)):
            with self.subTest(plataforma=modulo.__name__), tempfile.TemporaryDirectory() as carpeta:
                error, fin = Mock(), Mock()
                motor = clase(Mock(), Mock(), fin, error)
                with patch.object(modulo.yt_dlp, 'YoutubeDL') as fabrica, \
                     patch.object(modulo, 'descargar_enlace', side_effect=spotify.ErrorSpotify('Playlist privada')):
                    motor._trabajo(URL, Path(carpeta))
                    opciones = fabrica.call_args.args[0]
                    self.assertTrue(opciones['noplaylist'])
                    self.assertIn('spotify_id', opciones['outtmpl'])
                    error.assert_called_once_with('Spotify: Playlist privada')
                    fin.assert_not_called()


if __name__ == '__main__':
    unittest.main()
