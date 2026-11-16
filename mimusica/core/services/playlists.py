"""Playlists persistentes en un archivo JSON."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from mimusica.core.models import Cancion, Playlist


class RepositorioPlaylists:
    def __init__(self, archivo: Path):
        self._archivo = archivo
        self._listas: list[Playlist] = []
        self._cargar()

    # ---- persistencia ------------------------------------------------------
    def _cargar(self) -> None:
        try:
            datos = json.loads(self._archivo.read_text(encoding="utf-8"))
            self._listas = [
                Playlist(str(d["id"]), str(d["nombre"]), [str(a) for a in d.get("archivos", [])])
                for d in datos.get("playlists", [])
            ]
        except (OSError, ValueError, KeyError, TypeError):
            self._listas = []  # sin archivo, o dañado: se empieza vacío

    def _guardar(self) -> None:
        """Escritura atómica: primero a un temporal y luego se reemplaza el archivo."""
        try:
            self._archivo.parent.mkdir(parents=True, exist_ok=True)
            temporal = self._archivo.with_suffix(".tmp")
            contenido = {"playlists": [
                {"id": p.id, "nombre": p.nombre, "archivos": p.archivos} for p in self._listas]}
            temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporal, self._archivo)
        except OSError:
            pass  # no poder guardar no debe cerrar la app

    # ---- operaciones -------------------------------------------------------
    def listar(self) -> list[Playlist]:
        return list(self._listas)

    def obtener(self, id_: str) -> Playlist | None:
        return next((p for p in self._listas if p.id == id_), None)

    def crear(self, nombre: str) -> Playlist:
        nombre = " ".join((nombre or "").split()) or "Nueva playlist"
        lista = Playlist(uuid.uuid4().hex[:10], nombre, [])
        self._listas.append(lista)
        self._guardar()
        return lista

    def eliminar(self, id_: str) -> None:
        self._listas = [p for p in self._listas if p.id != id_]
        self._guardar()

    def renombrar(self, id_: str, nombre: str) -> None:
        lista = self.obtener(id_)
        nombre = " ".join((nombre or "").split())
        if lista and nombre:
            lista.nombre = nombre
            self._guardar()

    def agregar(self, id_: str, archivo: str) -> bool:
        """Añade un archivo (por nombre). Devuelve False si ya estaba."""
        lista = self.obtener(id_)
        if lista is None or archivo in lista.archivos:
            return False
        lista.archivos.append(archivo)
        self._guardar()
        return True

    def quitar(self, id_: str, archivo: str) -> None:
        lista = self.obtener(id_)
        if lista and archivo in lista.archivos:
            lista.archivos.remove(archivo)
            self._guardar()

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
