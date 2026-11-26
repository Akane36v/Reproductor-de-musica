"""Regresiones de caché, búsqueda y navegación con una página de prueba."""
import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock, patch

import flet as ft

from mimusica.ui import app
from mimusica.ui.covers import CachePortadas
from mimusica.ui.player_views import Acciones, MiniReproductor
from mimusica.core.models import Cancion
from mimusica.core.ports import Plataforma
from mimusica.core.services.playlists import RepositorioPlaylists


def recorrer(control):
    yield control
    for nombre in ('controls', 'content', 'suffix', 'actions', 'title'):
        valor = getattr(control, nombre, None)
        for hijo in valor if isinstance(valor, list) else [valor]:
            if isinstance(hijo, ft.Control):
                yield from recorrer(hijo)


class Pagina:
    def __init__(self):
        self.width, self.height = 390, 800
        self.window = SimpleNamespace()
        self.media = SimpleNamespace(view_insets=SimpleNamespace(bottom=0))
        self.controls, self.services, self.overlay, self.dialogos = [], [], [], []
        self.loop = asyncio.get_running_loop()
    def add(self, *controles): self.controls.extend(controles)
    def update(self): pass
    def run_task(self, funcion, *args):
        if funcion.__name__ != 'bucle_reproduccion':
            return asyncio.run_coroutine_threadsafe(funcion(*args), self.loop)
    def show_dialog(self, dialogo): self.dialogos.append(dialogo)
    def pop_dialog(self): self.dialogos.pop()


class Cache(unittest.TestCase):
    def test_limita_bytes_y_conserva_lo_usado_recientemente(self):
        cache = CachePortadas(max_elementos=3, max_bytes=6)
        cache.guardar('a', b'aa')
        cache.guardar('b', b'bb')
        cache.guardar('c', b'cc')
        cache.get('a')
        cache.guardar('d', b'dd')
        self.assertIn('a', cache)
        self.assertNotIn('b', cache)
        cache.guardar('enorme', b'1234567')
        self.assertNotIn('enorme', cache)
        self.assertIn('a', cache)

    def test_lecturas_concurrentes_reutilizan_archivo_y_ausencia_de_portada(self):
        for resultado in (b'imagen', None):
            cache, lector = CachePortadas(), Mock(return_value=resultado)
            with ThreadPoolExecutor(max_workers=4) as executor:
                resultados = list(executor.map(lambda _: cache.leer('ruta', lector), range(20)))
            self.assertEqual(resultados, [resultado] * 20)
            lector.assert_called_once_with('ruta')
            cache.invalidar()
            cache.leer('ruta', lector)
            self.assertEqual(lector.call_count, 2)

    def test_eliminar_actualiza_el_presupuesto(self):
        cache = CachePortadas(max_bytes=4)
        cache.guardar('a', b'abcd')
        cache.pop('a')
        cache.guardar('b', b'abcd')
        self.assertEqual(cache.get('b'), b'abcd')

    def test_escaneo_descarta_lectura_iniciada_antes_de_invalidar(self):
        cache = CachePortadas()
        iniciada, continuar = Event(), Event()
        def leer(_):
            iniciada.set()
            continuar.wait(2)
            return b'antigua'
        with ThreadPoolExecutor(max_workers=1) as executor:
            tarea = executor.submit(cache.leer, 'ruta', leer)
            self.assertTrue(iniciada.wait(2))
            cache.invalidar()
            continuar.set()
            tarea.result(2)
        self.assertNotIn('ruta', cache)

    def test_mini_recupera_progreso_al_terminar_la_carga(self):
        mini = MiniReproductor(Acciones(*([lambda *args: None] * 11)))
        mini.progreso(50, 1000)
        mini.cargando(True)
        self.assertIsNone(mini.barra.value)
        mini.cargando(False)
        self.assertEqual(mini.barra.value, 0.05)


class Interfaz(unittest.IsolatedAsyncioTestCase):
    async def test_busqueda_rapida_paginacion_playlists_y_dialogos(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            canciones = [Cancion(str(carpeta / f'{i}.mp3'), f'Canción {i}',
                                'Artista', 'Álbum', 180) for i in range(180)]
            repo = RepositorioPlaylists(carpeta / 'playlists.json')
            favorita = repo.crear('Favoritas')
            repo.agregar(favorita.id, '1.mp3')
            gestor = SimpleNamespace(ocupado=False, problema_de_entorno=lambda: None)
            plataforma = Plataforma('prueba', False, lambda: carpeta, lambda: carpeta,
                                    lambda **kwargs: gestor, lambda page: Mock())
            estados = []
            estado_original = app.EstadoApp
            def estado(carpeta):
                creado = estado_original(carpeta)
                estados.append(creado)
                return creado
            page = Pagina()
            with patch.object(app, 'EstadoApp', side_effect=estado), \
                 patch.object(app, 'escanear_biblioteca', return_value=canciones), \
                 patch.object(app, 'leer_portada', return_value=None), \
                 patch.object(ft.Control, 'update', return_value=None):
                app.main(page, plataforma)
                await asyncio.sleep(0.1)
                est = estados[0]
                def controles():
                    return [c for raiz in page.controls for c in recorrer(raiz)]
                self.assertEqual(len(est.visibles), 180)
                self.assertEqual(est.mostrando, 60)
                campo = next(c for c in controles() if isinstance(c, ft.TextField)
                             and c.hint_text == 'Buscar en tu biblioteca')
                generacion = est.generacion
                tareas = []
                for texto in ('c', 'ca', 'canción 12'):
                    campo.value = texto
                    tareas.append(asyncio.create_task(campo.on_change(None)))
                    await asyncio.sleep(0.02)
                await asyncio.gather(*tareas)
                self.assertEqual(est.generacion, generacion + 1)
                self.assertEqual(len(est.visibles), 11)
                campo.suffix.on_click(None)
                self.assertEqual(len(est.visibles), 180)
                next(c for c in controles() if isinstance(c, ft.Container) and c.tooltip == 'Favoritas').on_click(None)
                self.assertEqual(len(est.visibles), 1)
                next(c for c in controles() if isinstance(c, ft.IconButton) and c.tooltip == 'Nueva playlist').on_click(None)
                self.assertEqual(page.dialogos[-1].bgcolor, page.theme.color_scheme.surface)
                page.pop_dialog()
                next(c for c in controles() if isinstance(c, ft.IconButton) and c.tooltip.startswith('Opciones de')).on_click(None)
                self.assertEqual(page.dialogos[-1].bgcolor, page.theme.color_scheme.surface)
                page.on_disconnect(None)


if __name__ == '__main__':
    unittest.main()
