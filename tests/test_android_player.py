"""Regresiones de segundo plano y selección rápida, sin un dispositivo Android."""
import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft
from mimusica.adapters.android import player


class AudioSimulado:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.posicion = 0
        self.ordenes = []
        self.cargado = False

    async def release(self):
        self.ordenes.append("release")

    async def play(self, position=0):
        self.ordenes.append("play")
        self.posicion = player._a_ms(position)
        self.on_state_change(SimpleNamespace(control=self, state="playing"))

    async def pause(self):
        self.ordenes.append("pause")

    async def resume(self):
        self.ordenes.append("resume")
        self.on_state_change(SimpleNamespace(control=self, state="playing"))

    async def seek(self, position):
        self.posicion = player._a_ms(position)
        self.ordenes.append("seek")

    async def get_current_position(self):
        return ft.Duration(milliseconds=self.posicion)

    def update(self):
        pass


class PaginaSimulada:
    def __init__(self):
        self.services = []
        self.tareas = []
        self.creados = []
        self.dialogos = []
        self.cargar = True

    def run_task(self, funcion, *args):
        if funcion.__name__ == "_vigilar":
            return
        tarea = asyncio.create_task(funcion(*args))
        self.tareas.append(tarea)
        return tarea

    def update(self):
        for audio in self.services:
            if audio not in self.creados:
                self.creados.append(audio)
            if self.cargar and not audio.cargado:
                audio.cargado = True
                audio.on_loaded(SimpleNamespace(control=audio))
                audio.on_duration_change(SimpleNamespace(control=audio, duration=180000))

    def show_dialog(self, dialogo):
        self.dialogos.append(dialogo)

    async def terminar(self):
        await asyncio.gather(*self.tareas)


class PruebasAudio(unittest.IsolatedAsyncioTestCase):
    async def test_comando_nativo_que_no_responde_expira_y_permite_nueva_pista(self):
        async def bloqueado(*args, **kwargs):
            await asyncio.Event().wait()
        with patch.object(AudioSimulado, 'play', bloqueado), patch.object(player, 'ESPERA_COMANDO_S', 0.02):
            await self.iniciar()
        self.assertTrue(self.motor.tomar_error())
        self.assertFalse(self.motor.activo)
        self.motor.reproducir('segunda.m4a')
        await self.pagina.terminar()
        self.assertTrue(self.motor.activo)
        self.assertFalse(self.motor._operacion.locked())

    def setUp(self):
        self.parches = [
            patch.object(player.fta, "Audio", AudioSimulado),
            patch.object(player, "ESPERA_SELECCION_S", 0),
            patch.object(player, "ESPERA_CARGA_RUTA_S", 0.2),
        ]
        for parche in self.parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.pagina = PaginaSimulada()
        self.motor = player.ReproductorFlet(self.pagina)

    async def iniciar(self):
        self.motor.reproducir("primera.m4a")
        await self.pagina.terminar()

    async def test_avanza_sin_eventos_de_flutter(self):
        await self.iniciar()
        audio = self.motor._audio
        self.motor.en_segundo_plano(True)
        for indice in range(1, 30):
            self.motor._ultimo_avance = time.monotonic() - 10
            audio.posicion = indice * 1000
            await self.motor._revisar()
        self.assertEqual(audio.ordenes, ["play"])
        self.assertEqual(self.motor._intentos, 0)
        self.assertEqual(self.motor._pos_base, 29000)

    async def test_playing_sin_avance_no_confirma_recuperacion(self):
        await self.iniciar()
        for intento in (1, 2):
            self.motor._ultimo_avance = time.monotonic() - 10
            await self.motor._revisar()
            self.assertEqual(self.motor._intentos, intento)
        self.motor._ultimo_avance = time.monotonic() - 10
        await self.motor._revisar()
        self.assertTrue(self.motor.tomar_error())
        self.assertFalse(self.motor.activo)
        self.assertEqual(len(self.pagina.dialogos), 1)
        self.assertEqual(len(self.pagina.services), 0)

    async def test_rafaga_solo_carga_ultima(self):
        for indice in range(30):
            self.motor.reproducir(f"pista{indice}.m4a")
        await self.pagina.terminar()
        self.assertEqual(len(self.pagina.creados), 1)
        self.assertEqual(self.motor._audio.src, "pista29.m4a")

    async def test_cambio_durante_preparacion(self):
        self.pagina.cargar = False
        self.motor.reproducir("vieja.m4a")
        await asyncio.sleep(0.01)
        vieja = self.motor._audio
        self.motor.reproducir("intermedia.m4a")
        self.motor.reproducir("ultima.m4a")
        self.pagina.cargar = True
        self.pagina.update()
        await self.pagina.terminar()
        self.assertEqual(vieja.ordenes, ["release"])
        self.assertEqual(self.motor._audio.src, "ultima.m4a")
        self.assertEqual(len(self.pagina.services), 1)
        self.assertEqual(len(self.pagina.creados), 2)

    async def test_detener_durante_carga_invalida_play(self):
        self.pagina.cargar = False
        self.motor.reproducir("vieja.m4a")
        await asyncio.sleep(0.01)
        vieja = self.motor._audio
        self.motor.detener()
        self.pagina.cargar = True
        self.pagina.update()
        await self.pagina.terminar()
        self.assertNotIn("play", vieja.ordenes)
        self.assertFalse(self.motor.activo)
        self.assertEqual(len(self.pagina.services), 0)

    async def test_pausa_durante_carga(self):
        self.pagina.cargar = False
        self.motor.reproducir("pista.m4a")
        await asyncio.sleep(0.01)
        self.motor.pausar()
        self.pagina.cargar = True
        self.pagina.update()
        await self.pagina.terminar()
        self.assertNotIn("play", self.motor._audio.ordenes)
        self.motor.reanudar()
        await self.pagina.terminar()
        self.assertIn("resume", self.motor._audio.ordenes)

    async def test_eventos_antiguos_no_finalizan_nueva_pista(self):
        await self.iniciar()
        anterior = self.motor._audio
        self.motor.reproducir("nueva.m4a")
        await self.pagina.terminar()
        self.motor._al_cambiar_estado(SimpleNamespace(control=anterior, state="completed"))
        self.assertFalse(self.motor.terminado())
        self.assertEqual(anterior.ordenes[-1], "release")

    async def test_fin_sin_completed_requiere_posicion_real(self):
        await self.iniciar()
        self.motor._audio.posicion = 179500
        self.motor._pos_base = 179500
        self.motor._ultimo_avance = time.monotonic() - 10
        await self.motor._revisar()
        self.assertTrue(self.motor.terminado())
        self.assertNotIn("resume", self.motor._audio.ordenes)

    async def test_respuesta_de_posicion_obsoleta_se_descarta(self):
        await self.iniciar()
        entrada = asyncio.Event()
        salida = asyncio.Event()

        async def lenta():
            entrada.set()
            await salida.wait()
            return ft.Duration(seconds=80)

        self.motor._audio.get_current_position = lenta
        revision = asyncio.create_task(self.motor._revisar())
        await entrada.wait()
        self.motor.reproducir("nueva.m4a")
        salida.set()
        await revision
        await self.pagina.terminar()
        self.assertEqual(self.motor._pos_base, 0)
        self.assertEqual(self.motor._audio.src, "nueva.m4a")


if __name__ == "__main__":
    unittest.main()
