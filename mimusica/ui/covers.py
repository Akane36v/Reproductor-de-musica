"""Caché compartida y acotada para las portadas de lista y reproductor."""
from collections import OrderedDict
from threading import RLock, Event


class CachePortadas:
    def __init__(self, max_elementos=300, max_bytes=24 * 1024 * 1024):
        self.max_elementos = max_elementos
        self.max_bytes = max_bytes
        self._datos = OrderedDict()
        self._bytes = 0
        self._generacion = 0
        self._bloqueo = RLock()
        self._lecturas = {}

    def __contains__(self, ruta):
        with self._bloqueo:
            return ruta in self._datos

    def get(self, ruta, defecto=None):
        with self._bloqueo:
            if ruta not in self._datos:
                return defecto
            self._datos.move_to_end(ruta)
            return self._datos[ruta]

    def guardar(self, ruta, datos):
        with self._bloqueo:
            anterior = self._datos.pop(ruta, None)
            self._bytes -= len(anterior or b'')
            # Una portada excesiva puede mostrarse sin permanecer en memoria.
            if len(datos or b'') > self.max_bytes:
                return
            self._datos[ruta] = datos
            self._bytes += len(datos or b'')
            while len(self._datos) > self.max_elementos or self._bytes > self.max_bytes:
                _, antigua = self._datos.popitem(last=False)
                self._bytes -= len(antigua or b'')

    def leer(self, ruta, lector):
        # Cada archivo tiene su propia espera: uno lento no bloquea los demás.
        with self._bloqueo:
            if ruta in self._datos:
                return self.get(ruta)
            pendiente = self._lecturas.get(ruta)
            propietario = pendiente is None
            if propietario:
                pendiente = self._lecturas[ruta] = Event()
            generacion = self._generacion
        if not propietario:
            pendiente.wait(2)
            return self.get(ruta)
        try:
            datos = lector(ruta)
            with self._bloqueo:
                if generacion == self._generacion:
                    self.guardar(ruta, datos)
            return datos
        finally:
            with self._bloqueo:
                self._lecturas.pop(ruta, None)
                pendiente.set()

    def invalidar(self):
        with self._bloqueo:
            self._datos.clear()
            self._bytes = 0
            self._generacion += 1

    def pop(self, ruta, defecto=None):
        with self._bloqueo:
            self._generacion += 1
            datos = self._datos.pop(ruta, defecto)
            self._bytes -= len(datos or b'')
            return datos
