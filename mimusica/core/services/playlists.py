"""Playlists persistentes en un archivo JSON."""

from __future__ import annotations

import json
import os
import uuid
import tempfile
from functools import wraps
from threading import RLock
from pathlib import Path

from mimusica.core.models import Cancion, Playlist
from mimusica.core.diagnostico import registrar


def serializado(metodo):
    @wraps(metodo)
    def ejecutar(self, *args, **kwargs):
        with self._bloqueo:
            return metodo(self, *args, **kwargs)
    return ejecutar


class RepositorioPlaylists:
    def __init__(self, archivo: Path):
        self._archivo = archivo
        self._listas: list[Playlist] = []
        self._bloqueo = RLock()
        self.ultimo_error = None
        self.recuperado = False
        self._persistido = None
        self._cargar()

    # ---- persistencia ------------------------------------------------------
    def _cargar(self) -> None:
        for archivo in (self._archivo, self._archivo.with_suffix('.json.bak')):
            try:
                texto = archivo.read_text(encoding='utf-8')
                datos = json.loads(texto)
                if not isinstance(datos, dict) or not isinstance(datos.get('playlists'), list):
                    raise ValueError('Estructura de playlists inválida')
                listas = []
                ids = set()
                for d in datos['playlists']:
                    if (not isinstance(d, dict) or not isinstance(d.get('id'), str)
                            or not isinstance(d.get('nombre'), str)
                            or not isinstance(d.get('archivos', []), list)
                            or not all(isinstance(a, str) for a in d.get('archivos', []))
                            or d['id'] in ids):
                        raise ValueError('Playlist inválida')
                    ids.add(d['id'])
                    listas.append(Playlist(d['id'], d['nombre'], d.get('archivos', [])))
                self._listas, self._persistido = listas, texto
                self.recuperado = archivo != self._archivo
                self.ultimo_error = None
                return
            except FileNotFoundError:
                continue
            except (OSError, ValueError, TypeError) as ex:
                registrar('playlists', f'No se pudo leer {archivo.name}: {ex}')
                self.ultimo_error = 'No se pudo leer el archivo de playlists.'
        self._listas = []

    @staticmethod
    def _escribir_atomico(archivo, texto):
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=archivo.parent,
                                              prefix=archivo.name, suffix='.tmp', delete=False) as flujo:
                temporal = Path(flujo.name)
                flujo.write(texto)
                flujo.flush()
                os.fsync(flujo.fileno())
            os.replace(temporal, archivo)
        finally:
            if temporal is not None:
                temporal.unlink(missing_ok=True)

    def _guardar(self) -> None:
        """Escritura atómica: primero a un temporal y luego se reemplaza el archivo."""
        try:
            self._archivo.parent.mkdir(parents=True, exist_ok=True)
            contenido = {"playlists": [
                {"id": p.id, "nombre": p.nombre, "archivos": p.archivos} for p in self._listas]}
            texto = json.dumps(contenido, ensure_ascii=False, indent=2)
            if self._persistido is not None:
                self._escribir_atomico(self._archivo.with_suffix('.json.bak'), self._persistido)
            self._escribir_atomico(self._archivo, texto)
            self._persistido = texto
            self.ultimo_error = None
        except OSError as ex:
            self.ultimo_error = 'Los cambios están en memoria, pero no se pudieron guardar. Revisa el espacio y los permisos.'
            registrar('playlists', f'Error de guardado: {ex}')

    # ---- operaciones -------------------------------------------------------
    @serializado
    def listar(self) -> list[Playlist]:
        return list(self._listas)

    @serializado
    def obtener(self, id_: str) -> Playlist | None:
        return next((p for p in self._listas if p.id == id_), None)

    @serializado
    def crear(self, nombre: str) -> Playlist:
        nombre = " ".join((nombre or "").split()) or "Nueva playlist"
        lista = Playlist(uuid.uuid4().hex[:10], nombre, [])
        self._listas.append(lista)
        self._guardar()
        return lista

    @serializado
    def eliminar(self, id_: str) -> None:
        self._listas = [p for p in self._listas if p.id != id_]
        self._guardar()

    @serializado
    def renombrar(self, id_: str, nombre: str) -> None:
        lista = self.obtener(id_)
        nombre = " ".join((nombre or "").split())
        if lista and nombre:
            lista.nombre = nombre
            self._guardar()

    @serializado
    def agregar(self, id_: str, archivo: str) -> bool:
        """Añade un archivo (por nombre). Devuelve False si ya estaba."""
        lista = self.obtener(id_)
        if lista is None or archivo in lista.archivos:
            return False
        lista.archivos.append(archivo)
        self._guardar()
        return True

    @serializado
    def quitar(self, id_: str, archivo: str) -> None:
        lista = self.obtener(id_)
        if lista and archivo in lista.archivos:
            lista.archivos.remove(archivo)
            self._guardar()

    @serializado
    def quitar_de_todas(self, archivo: str) -> None:
        """Quita un archivo de TODAS las playlists (al borrar la canción)."""
        cambio = False
        for lista in self._listas:
            if archivo in lista.archivos:
                lista.archivos = [a for a in lista.archivos if a != archivo]
                cambio = True
        if cambio:
            self._guardar()

    @staticmethod
    def resolver(lista: Playlist, biblioteca: list[Cancion]) -> list[Cancion]:
        """Convierte los nombres guardados en canciones existentes, respetando el orden."""
        por_nombre = {Path(c.ruta).name: c for c in biblioteca}
        return [por_nombre[a] for a in lista.archivos if a in por_nombre]
