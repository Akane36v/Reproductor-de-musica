"""Audio Android con cargas serializadas y vigilancia de la posición real.

Los eventos de posición de audioplayers dependen de los fotogramas de Flutter.
En segundo plano se consulta el motor directamente. Cada fuente tiene su propio
control y se libera la anterior antes de montar otra.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import flet as ft
import flet_audio as fta

from mimusica.core.diagnostico import registrar

ESPERA_CARGA_RUTA_S = 4.0
ESPERA_CARGA_BYTES_S = 12.0
ESPERA_COMANDO_S = 8.0
INTERVALO_VIGILANTE_S = 1.0
UMBRAL_SILENCIO_S = 6.0
INTERVALO_DIAGNOSTICO_S = 15.0
VENTANA_EVENTOS_PROPIOS_S = 1.5
ESPERA_SELECCION_S = 0.15


def _a_ms(valor) -> int:
    """Normaliza las duraciones devueltas por Flet."""
    if valor is None:
        return 0
    if isinstance(valor, (int, float)):
        return int(valor)
    if hasattr(valor, "total_seconds"):
        return int(valor.total_seconds() * 1000)
    return int(
        (getattr(valor, "days", 0) or 0) * 86_400_000
        + (getattr(valor, "hours", 0) or 0) * 3_600_000
        + (getattr(valor, "minutes", 0) or 0) * 60_000
        + (getattr(valor, "seconds", 0) or 0) * 1000
        + (getattr(valor, "milliseconds", 0) or 0)
    )


class ReproductorFlet:
    def __init__(self, page: ft.Page):
        self._page = page
        self._audio = None
        self._audio_generacion = -1
        self._generacion = 0
        self._operacion = asyncio.Lock()
        self._volumen = 1.0
        self._usar_bytes = False
        self._ruta_actual = ""
        self._inicio_ms = 0
        self._dur_ms = 0
        self._pos_base = 0
        self._pos_t = time.monotonic()
        self._ultimo_avance = self._pos_t
        self._ultimo_diagnostico = 0.0
        self._ignorar_hasta = 0.0
        self._activo = False
        self._pausado = False
        self._terminado = False
        self._sono = False
        self._cargando_pista = False
        self._recuperando = False
        self._intentos = 0
        self._vigilante_iniciado = False
        self._segundo_plano = False
        self._error_pendiente = False
        self._cambio_externo = None
        registrar("audio", "reproductor v2: consulta de posición y cargas serializadas")

    def _es_actual(self, e):
        return (getattr(e, "control", None) is self._audio
                and self._audio_generacion == self._generacion and self._activo)

    def _al_cambiar_duracion(self, e):
        if self._es_actual(e):
            self._dur_ms = _a_ms(e.duration)

    def _al_cambiar_estado(self, e):
        if not self._es_actual(e):
            return
        nombre = str(getattr(e.state, "value", e.state)).lower()
        registrar("audio", f"estado {nombre}")
        propio = (self._cargando_pista or self._recuperando
                  or time.monotonic() < self._ignorar_hasta)
        if nombre == "playing":
            self._sono = True
            if self._pausado and not propio:
                self._pausado = False
                self._ultimo_avance = time.monotonic()
                self._cambio_externo = "reanuda"
        elif nombre == "completed" and not self._cargando_pista:
            self._terminado = True
        elif nombre in ("paused", "stopped") and not propio and not self._terminado:
            self._pausado = True
            self._cambio_externo = "pausa"
            registrar("audio", "pausa externa comunicada por el motor")

    def _fallar(self, ex):
        self._activo = False
        self._cargando_pista = False
        self._error_pendiente = True
        detalle = f"{type(ex).__name__}: {ex}"
        registrar("audio", f"ERROR: {detalle}")
        try:
            self._page.show_dialog(ft.AlertDialog(
                modal=True, title=ft.Text("No se pudo reproducir"),
                content=ft.Text(detalle, selectable=True),
                actions=[ft.TextButton("Aceptar", on_click=lambda e: self._page.pop_dialog())],
            ))
        except Exception:
            pass

    def tomar_error(self):
        hubo, self._error_pendiente = self._error_pendiente, False
        return hubo

    def tomar_cambio_externo(self):
        cambio, self._cambio_externo = self._cambio_externo, None
        return cambio

    def en_segundo_plano(self, activo):
        self._segundo_plano = activo
        registrar("audio", "segundo plano" if activo else "primer plano")

    async def _liberar_audio(self):
        audio, self._audio = self._audio, None
        if audio is None:
            return
        try:
            await asyncio.wait_for(audio.release(), ESPERA_COMANDO_S)
        except Exception as ex:
            registrar("audio", f"liberación: {type(ex).__name__}: {ex}")
        finally:
            # Flet compara controles por valor. Aquí se elimina por identidad.
            for indice, servicio in enumerate(self._page.services):
                if servicio is audio:
                    del self._page.services[indice]
                    break
            self._page.update()

    async def _montar(self, fuente, mia, limite):
        cargado = asyncio.Event()

        def al_cargar(e):
            cargado.set()
            registrar("audio", f"fuente cargada solicitud={mia}")

        self._audio_generacion = mia
        self._audio = fta.Audio(
            src=fuente, autoplay=False, volume=self._volumen,
            release_mode=fta.ReleaseMode.STOP, on_loaded=al_cargar,
            on_duration_change=self._al_cambiar_duracion,
            on_state_change=self._al_cambiar_estado,
        )
        self._page.services.append(self._audio)
        self._page.update()
        # Se deja concluir la preparación nativa antes de liberar. Una selección
        # nueva invalida el resultado, sin lanzar otra carga sobre el mismo motor.
        await asyncio.wait_for(cargado.wait(), limite)

    async def _preparar(self, mia, ruta):
        await self._liberar_audio()
        if mia != self._generacion:
            return
        if not self._usar_bytes:
            try:
                await self._montar(ruta, mia, ESPERA_CARGA_RUTA_S)
                return
            except TimeoutError:
                if mia != self._generacion:
                    return
                registrar("audio", "ruta sin confirmar; se intenta la fuente como bytes")
                await self._liberar_audio()
        if mia != self._generacion:
            return
        datos = await asyncio.to_thread(Path(ruta).read_bytes)
        if mia != self._generacion:
            return
        await self._montar(datos, mia, ESPERA_CARGA_BYTES_S)
        self._usar_bytes = True

    async def _cargar_y_reproducir(self, mia, ruta):
        await asyncio.sleep(ESPERA_SELECCION_S)
        async with self._operacion:
            if mia != self._generacion:
                return
            registrar("audio", f"cargar solicitud={mia}: {Path(ruta).name}")
            try:
                await self._preparar(mia, ruta)
                if mia != self._generacion:
                    return
                if not self._pausado:
                    await asyncio.wait_for(
                        self._audio.play(ft.Duration(milliseconds=self._inicio_ms)),
                        ESPERA_COMANDO_S)
                    if mia != self._generacion:
                        return
                    # Una pausa durante play() debe conservar la intención del usuario.
                    if self._pausado:
                        await asyncio.wait_for(self._audio.pause(), ESPERA_COMANDO_S)
                self._pos_base = self._inicio_ms
                self._pos_t = self._ultimo_avance = time.monotonic()
            except Exception as ex:
                if mia == self._generacion:
                    self._fallar(ex)
                await self._liberar_audio()
            finally:
                if mia == self._generacion:
                    self._cargando_pista = False
                    self._ignorar_hasta = time.monotonic() + VENTANA_EVENTOS_PROPIOS_S

    async def _comando(self, mia, nombre, *args):
        async with self._operacion:
            if mia != self._generacion or self._audio is None:
                return
            try:
                self._ignorar_hasta = time.monotonic() + VENTANA_EVENTOS_PROPIOS_S
                await asyncio.wait_for(getattr(self._audio, nombre)(*args), ESPERA_COMANDO_S)
            except Exception as ex:
                if mia == self._generacion:
                    self._fallar(ex)

    async def _detener(self, mia):
        async with self._operacion:
            if mia == self._generacion:
                await self._liberar_audio()

    async def _vigilar(self):
        anterior = time.monotonic()
        while True:
            await asyncio.sleep(INTERVALO_VIGILANTE_S)
            ahora = time.monotonic()
            if ahora - anterior > 5:
                registrar("vigilante", f"intervalo entre revisiones {ahora - anterior:.1f}s")
            anterior = ahora
            try:
                await self._revisar()
            except Exception as ex:
                registrar("vigilante", f"error interno: {type(ex).__name__}: {ex}")

    async def _revisar(self):
        if (not self._activo or self._pausado or self._terminado
                or self._cargando_pista or self._operacion.locked() or self._audio is None):
            return
        mia = self._generacion
        async with self._operacion:
            if mia != self._generacion or self._audio is None:
                return
            try:
                valor = await asyncio.wait_for(
                    self._audio.get_current_position(), ESPERA_COMANDO_S)
                if mia != self._generacion or self._pausado or self._terminado:
                    return
                if valor is None:
                    raise RuntimeError("el motor no devolvió la posición")
                posicion = _a_ms(valor)
                ahora = time.monotonic()
                if posicion > self._pos_base:
                    if self._intentos:
                        registrar("vigilante", "avance real confirmado; audio recuperado")
                    self._ultimo_avance = ahora
                    self._intentos = 0
                    self._sono = True
                self._pos_base, self._pos_t = posicion, ahora
                if ahora - self._ultimo_diagnostico >= INTERVALO_DIAGNOSTICO_S:
                    registrar("vigilante", f"posición real={posicion}ms duración={self._dur_ms}ms "
                              f"sin avance={ahora - self._ultimo_avance:.1f}s "
                              f"segundo_plano={self._segundo_plano}")
                    self._ultimo_diagnostico = ahora
                quieto = ahora - self._ultimo_avance
                if quieto < UMBRAL_SILENCIO_S:
                    return
                if self._dur_ms > 0 and posicion >= self._dur_ms - 1000:
                    self._terminado = True
                    registrar("vigilante", "fin de pista confirmado por posición")
                    return
                await self._recuperar(mia)
            except Exception as ex:
                if mia == self._generacion:
                    self._fallar(ex)
                    await self._liberar_audio()

    async def _recuperar(self, mia):
        self._recuperando = True
        self._intentos += 1
        registrar("vigilante", f"posición detenida en {self._pos_base}ms; intento {self._intentos}")
        try:
            if self._intentos == 1:
                await asyncio.wait_for(self._audio.resume(), ESPERA_COMANDO_S)
            elif self._intentos == 2:
                posicion = self._pos_base
                self._cargando_pista = True
                await self._preparar(mia, self._ruta_actual)
                if mia != self._generacion or self._pausado:
                    return
                await asyncio.wait_for(
                    self._audio.play(ft.Duration(milliseconds=posicion)), ESPERA_COMANDO_S)
                if mia != self._generacion:
                    return
                if self._pausado:
                    await asyncio.wait_for(self._audio.pause(), ESPERA_COMANDO_S)
                # Volver a la posición guardada no demuestra que se haya recuperado.
                self._pos_base = posicion
            else:
                raise TimeoutError("la posición del audio sigue detenida tras dos intentos")
        finally:
            if mia == self._generacion:
                self._ultimo_avance = time.monotonic()
                self._cargando_pista = False
            self._recuperando = False

    @property
    def activo(self):
        return self._activo

    def reproducir(self, ruta, inicio_ms=0):
        self._generacion += 1
        self._ruta_actual = ruta
        self._inicio_ms = inicio_ms
        self._pos_base = inicio_ms
        self._pos_t = self._ultimo_avance = time.monotonic()
        self._dur_ms = 0
        self._intentos = 0
        self._terminado = self._sono = self._pausado = False
        self._error_pendiente = False
        self._cambio_externo = None
        self._activo = self._cargando_pista = True
        self._page.run_task(self._cargar_y_reproducir, self._generacion, ruta)
        if not self._vigilante_iniciado:
            self._vigilante_iniciado = True
            self._page.run_task(self._vigilar)

    def pausar(self):
        if self._activo:
            self._pausado = True
            registrar("audio", "orden pausa")
            if not self._cargando_pista:
                self._page.run_task(self._comando, self._generacion, "pause")

    def reanudar(self):
        if self._activo:
            self._pausado = False
            self._ultimo_avance = time.monotonic()
            registrar("audio", "orden reanudar")
            if not self._cargando_pista:
                self._page.run_task(self._comando, self._generacion, "resume")

    def detener(self):
        self._generacion += 1
        self._activo = self._pausado = self._cargando_pista = False
        self._pos_base = 0
        registrar("audio", "orden detener")
        self._page.run_task(self._detener, self._generacion)

    def liberar(self):
        self.detener()

    def saltar(self, ms):
        self._inicio_ms = max(0, int(ms))
        self._pos_base = self._inicio_ms
        self._pos_t = self._ultimo_avance = time.monotonic()
        if self._activo and not self._cargando_pista:
            self._page.run_task(self._comando, self._generacion, "seek",
                                ft.Duration(milliseconds=self._inicio_ms))

    def posicion_ms(self):
        if self._activo and not self._pausado and self._sono and not self._terminado:
            # Limitar la interpolación impide una barra que avance indefinidamente
            # cuando el motor o el puente dejan de responder.
            return self._pos_base + int(min(time.monotonic() - self._pos_t, 1.0) * 1000)
        return self._pos_base

    def terminado(self):
        return self._activo and self._terminado

    def cargando(self):
        return self._activo and not self._pausado and self._cargando_pista

    def poner_volumen(self, valor):
        self._volumen = valor
        if self._audio:
            self._audio.volume = valor
            self._audio.update()
