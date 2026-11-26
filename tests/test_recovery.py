"""Fallos inyectados y concurrencia: comprueban recuperación y ausencia de esperas en la UI."""
import asyncio
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft
from mimusica.ui import app
from mimusica.ui.covers import CachePortadas
from mimusica.core.models import Cancion
from mimusica.core.ports import Plataforma
from mimusica.core.services import library
from mimusica.core.services.playlists import RepositorioPlaylists
from test_ui import Pagina, recorrer
from mimusica.adapters.android.downloader import DescargadorYtDlpAndroid
from mimusica.adapters.windows.downloader import DescargadorYtDlp


class Persistencia(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.archivo = Path(self.temporal.name) / 'playlists.json'

    def test_archivo_invalido_no_impide_arranque(self):
        for texto in ('[]', 'null', '12', '{', '{"playlists":null}',
                      '{"playlists":[{"id":"1","nombre":"A","archivos":null}]}'):
            self.archivo.write_text(texto)
            repo = RepositorioPlaylists(self.archivo)
            self.assertEqual(repo.listar(), [])
            self.assertIsNotNone(repo.ultimo_error)

    def test_recupera_ultimo_estado_respaldado(self):
        repo = RepositorioPlaylists(self.archivo)
        lista = repo.crear('Favoritas')
        repo.agregar(lista.id, 'a.mp3')
        repo.agregar(lista.id, 'b.mp3')
        self.archivo.write_text('{truncado')
        recuperado = RepositorioPlaylists(self.archivo)
        self.assertTrue(recuperado.recuperado)
        self.assertEqual(recuperado.obtener(lista.id).archivos, ['a.mp3'])
        recuperado.agregar(lista.id, 'c.mp3')
        self.assertEqual(RepositorioPlaylists(self.archivo).obtener(lista.id).archivos, ['a.mp3', 'c.mp3'])

    def test_guardado_fallido_conserva_archivo_y_permite_reintentar(self):
        repo = RepositorioPlaylists(self.archivo)
        lista = repo.crear('Favoritas')
        original = self.archivo.read_bytes()
        with patch('mimusica.core.services.playlists.os.replace', side_effect=PermissionError('sin permiso')):
            repo.agregar(lista.id, 'a.mp3')
        self.assertEqual(self.archivo.read_bytes(), original)
        self.assertIsNotNone(repo.ultimo_error)
        self.assertFalse(list(self.archivo.parent.glob('*.tmp')))
        repo.agregar(lista.id, 'b.mp3')
        self.assertIsNone(repo.ultimo_error)
        self.assertEqual(RepositorioPlaylists(self.archivo).obtener(lista.id).archivos, ['a.mp3', 'b.mp3'])

    def test_escrituras_simultaneas_no_pierden_canciones(self):
        repo = RepositorioPlaylists(self.archivo)
        lista = repo.crear('Favoritas')
        with ThreadPoolExecutor(max_workers=8) as ejecutor:
            list(ejecutor.map(lambda i: repo.agregar(lista.id, f'{i}.mp3'), range(80)))
        self.assertEqual(len(RepositorioPlaylists(self.archivo).obtener(lista.id).archivos), 80)
        json.loads(self.archivo.read_text())


class Archivos(unittest.TestCase):
    def test_portada_bloqueada_no_bloquea_otros_archivos(self):
        cache = CachePortadas()
        iniciada, terminar = Event(), Event()
        def lenta(_):
            iniciada.set()
            terminar.wait(2)
            return b'lenta'
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            pendiente = ejecutor.submit(cache.leer, 'lenta', lenta)
            try:
                self.assertTrue(iniciada.wait(1))
                rapida = ejecutor.submit(cache.leer, 'rapida', lambda _: b'rapida')
                self.assertEqual(rapida.result(0.5), b'rapida')
            finally:
                terminar.set()
                pendiente.result(1)

    def test_fallo_portada_suelta_esperas_y_permite_reintentar(self):
        cache = CachePortadas()
        with self.assertRaises(OSError):
            cache.leer('ruta', Mock(side_effect=OSError('dañado')))
        self.assertEqual(cache.leer('ruta', lambda _: b'valida'), b'valida')

    def test_duracion_no_finita_no_rompe_reproduccion(self):
        for valor in (float('nan'), float('inf'), -1):
            with patch.object(library, 'MutagenFile', return_value=SimpleNamespace(
                    info=SimpleNamespace(length=valor), tags={})):
                self.assertEqual(library.leer_cancion(Path('a.mp3')).duracion, 0)


class Descargas(unittest.TestCase):
    def test_fallo_inesperado_notifica_y_permite_iniciar_otra_descarga(self):
        for clase in (DescargadorYtDlpAndroid, DescargadorYtDlp):
            with self.subTest(clase=clase.__name__):
                error = Mock()
                motor = clase(Mock(), Mock(), Mock(), error)
                with patch.object(motor, '_trabajo', side_effect=RuntimeError('fallo de preparación')):
                    motor.iniciar('url', Path('.'))
                    motor._hilo.join(1)
                    error.assert_called_once()
                    self.assertFalse(motor.ocupado)
                with patch.object(motor, '_trabajo') as trabajo:
                    motor.iniciar('otra', Path('.'))
                    motor._hilo.join(1)
                    trabajo.assert_called_once()

    def test_inicios_simultaneos_solo_crean_una_descarga(self):
        for clase in (DescargadorYtDlpAndroid, DescargadorYtDlp):
            motor = clase(Mock(), Mock(), Mock(), Mock())
            terminar = Event()
            with patch.object(motor, '_trabajo', side_effect=lambda *args: terminar.wait(2)) as trabajo:
                try:
                    with ThreadPoolExecutor(max_workers=8) as ejecutor:
                        list(ejecutor.map(lambda _: motor.iniciar('url', Path('.')), range(40)))
                    self.assertEqual(trabajo.call_count, 1)
                finally:
                    terminar.set()
                    motor._hilo.join(1)


class RecuperacionUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.temporal.name)
        self.canciones = [Cancion(str(self.carpeta / f'{i}.mp3'), f'Tema {i}', 'Artista', '', 180) for i in range(3)]
        for cancion in self.canciones: Path(cancion.ruta).touch()
        self.motor = Mock(activo=True)
        self.motor.cargando.return_value = False
        self.motor.tomar_error.return_value = False
        self.motor.tomar_cambio_externo.return_value = None
        self.motor.terminado.return_value = False
        self.motor.posicion_ms.return_value = 100
        self.gestor = SimpleNamespace(ocupado=False, problema_de_entorno=lambda: None, iniciar=Mock())
        self.callbacks = {}
        def gestor(**kwargs):
            self.callbacks.update(kwargs)
            return self.gestor
        self.page = Pagina()
        self.funciones = {}
        original_task = self.page.run_task
        def run_task(funcion, *args):
            self.funciones[funcion.__name__] = funcion
            return original_task(funcion, *args)
        self.page.run_task = run_task
        estados = []
        original = app.EstadoApp
        def estado(carpeta):
            creado = original(carpeta)
            estados.append(creado)
            return creado
        self.scan = patch.object(app, 'escanear_biblioteca', return_value=self.canciones)
        self.parches = [self.scan, patch.object(app, 'EstadoApp', side_effect=estado),
                        patch.object(app, 'leer_portada', return_value=None),
                        patch.object(ft.Control, 'update', return_value=None)]
        for p in self.parches: p.start()
        self.escaner = app.escanear_biblioteca
        plataforma = Plataforma('prueba', False, lambda: self.carpeta, lambda: self.carpeta,
                                gestor, lambda page: self.motor)
        app.main(self.page, plataforma)
        self.est = estados[0]
        await asyncio.sleep(0.08)

    async def asyncTearDown(self):
        self.page.on_disconnect(None)
        await asyncio.sleep(0.05)
        for p in reversed(self.parches): p.stop()
        self.temporal.cleanup()

    def controles(self):
        return [c for raiz in self.page.controls for c in recorrer(raiz)]

    def boton(self, tooltip):
        return next(c for c in self.controles() if isinstance(c, ft.IconButton) and c.tooltip == tooltip)

    async def test_escaneo_falla_conserva_lista_y_reintenta(self):
        self.escaner.side_effect = OSError('disco desconectado')
        self.boton('Actualizar biblioteca').on_click(None)
        await asyncio.sleep(0.08)
        self.assertEqual(self.est.biblioteca, self.canciones)
        self.escaner.side_effect = None
        self.escaner.return_value = self.canciones[:1]
        self.boton('Actualizar biblioteca').on_click(None)
        await asyncio.sleep(0.08)
        self.assertEqual(len(self.est.biblioteca), 1)

    async def test_escaneo_lento_expira_sin_bloquear_y_recupera(self):
        terminar = Event()
        self.escaner.side_effect = lambda *args: (terminar.wait(2), self.canciones)[1]
        try:
            with patch.object(app, 'ESPERA_ESCANEO_S', 0.03):
                self.boton('Actualizar biblioteca').on_click(None)
                await asyncio.sleep(0.08)
            self.assertEqual(self.est.biblioteca, self.canciones)
            self.assertTrue(any(isinstance(c, ft.Text) and 'No se pudo actualizar' in c.value for c in self.controles()))
            self.escaner.side_effect = None
            self.escaner.return_value = self.canciones[:1]
            self.boton('Actualizar biblioteca').on_click(None)
            await asyncio.sleep(0.08)
            self.assertEqual(len(self.est.biblioteca), 1)
        finally:
            terminar.set()

    async def test_reconexion_recrea_trabajadores(self):
        self.page.on_disconnect(None)
        self.page.on_connect(None)
        await asyncio.sleep(0.08)
        self.assertTrue(self.est.conectada)
        self.assertEqual(len(self.est.biblioteca), 3)

    async def test_carpeta_nueva_descarta_resultado_del_escaneo_anterior(self):
        iniciada, terminar = Event(), Event()
        def escanear(carpeta, extensiones):
            if carpeta == self.carpeta:
                iniciada.set()
                terminar.wait(2)
                return self.canciones
            return self.canciones[:1]
        self.escaner.side_effect = escanear
        self.boton('Actualizar biblioteca').on_click(None)
        try:
            await asyncio.sleep(0.03)
            self.assertTrue(iniciada.is_set())
            self.est.carpeta = self.carpeta / 'nueva'
            self.boton('Actualizar biblioteca').on_click(None)
            await asyncio.sleep(0.08)
            self.assertEqual(len(self.est.biblioteca), 1)
            terminar.set()
            await asyncio.sleep(0.08)
            self.assertEqual(len(self.est.biblioteca), 1)
        finally:
            terminar.set()

    async def test_programador_cerrado_no_actualiza_desde_otro_hilo(self):
        self.page.run_task = Mock(side_effect=RuntimeError('sesión cerrada'))
        self.page.update = Mock()
        self.callbacks['on_estado']('Descargando')
        self.page.update.assert_not_called()

    async def test_inicio_audio_atascado_libera_interfaz_sin_superponer_cargas(self):
        terminar = Event()
        self.motor.reproducir.side_effect = lambda *args: terminar.wait(2)
        self.boton('Reproducir').on_click(None)
        try:
            with patch.object(app, 'ESPERA_INICIO_AUDIO_S', 0.03):
                await asyncio.sleep(0.25)
                self.assertFalse(self.est.cargando_pista)
                self.assertFalse(self.est.reproduciendo)
                await asyncio.wait_for(self.funciones['reproducir_actual'](), 0.4)
                self.assertEqual(self.motor.reproducir.call_count, 1)
            terminar.set()
            await asyncio.sleep(0.05)
            self.motor.detener.assert_called()
            self.motor.reproducir.side_effect = None
            await asyncio.wait_for(self.funciones['reproducir_actual'](), 0.5)
            self.assertTrue(self.est.reproduciendo)
        finally:
            terminar.set()

    async def test_callback_tras_desconexion_no_toca_la_pagina(self):
        self.page.on_disconnect(None)
        self.page.update = Mock()
        self.callbacks['on_estado']('Descargando 50%')
        await asyncio.sleep(0.03)
        self.page.update.assert_not_called()

    async def test_fallo_inicio_descarga_restaura_el_boton(self):
        campo = next(c for c in self.controles() if isinstance(c, ft.TextField) and c.label == 'Enlace de música')
        campo.value = 'https://youtu.be/2K-evRnwcSc'
        boton = next(c for c in self.controles() if isinstance(c, ft.FilledButton) and c.content == 'Descargar audio')
        self.gestor.iniciar.side_effect = OSError('no se pudo iniciar hilo')
        boton.on_click(None)
        self.assertFalse(boton.disabled)
        self.gestor.iniciar.side_effect = None
        boton.on_click(None)
        self.assertEqual(self.gestor.iniciar.call_count, 2)

    async def test_motor_falla_repetidamente_y_permite_reintentar(self):
        self.est.reproduciendo = True
        self.motor.posicion_ms.side_effect = RuntimeError('puente no disponible')
        tarea = asyncio.create_task(self.funciones['bucle_reproduccion']())
        try:
            await asyncio.sleep(0.85)
            self.assertFalse(self.est.reproduciendo)
            self.motor.detener.assert_called()
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)

    async def test_portada_lenta_no_retiene_bloqueo_de_cambio_de_pista(self):
        terminar, iniciada = Event(), Event()
        self.est.portadas.invalidar()
        def leer(_):
            iniciada.set()
            terminar.wait(2)
            return None
        with patch.object(app, 'leer_portada', side_effect=leer):
            self.est.cola.cargar(self.canciones)
            # El botón de lista programa reproducir_actual; una portada lenta no debe retenerlo.
            self.boton('Reproducir').on_click(None)
            try:
                await asyncio.sleep(0.25)
                primera = self.funciones['reproducir_actual']
                self.est.cola.siguiente()
                await asyncio.wait_for(primera(), 0.5)
                self.assertGreaterEqual(self.motor.reproducir.call_count, 2)
            finally:
                terminar.set()


if __name__ == '__main__': unittest.main()
