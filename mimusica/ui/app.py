"""Interfaz de usuario (Flet). Solo conoce el núcleo y los puertos, nunca los adaptadores."""

from __future__ import annotations

import asyncio
import random
import threading
import inspect
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import flet as ft

from mimusica.core import diagnostico
from mimusica.core.errors import mensaje_error_amigable
from mimusica.core.formatting import formato_tiempo
from mimusica.core.models import Cancion
from mimusica.core.ports import Plataforma
from mimusica.core.services.covers import leer_portada
from mimusica.core.services.library import eliminar_archivo, escanear_biblioteca
from mimusica.core.services.playlists import RepositorioPlaylists
from mimusica.core.services.queue import ColaReproduccion
from mimusica.core.urls import validar_url
from mimusica.ui.player_views import Acciones, BarraEscritorio, MiniReproductor, ReproductorCompleto
from mimusica.ui.covers import CachePortadas
from mimusica.ui.theme import (
    ANCHO_MODO_ESCRITORIO, COLOR_ACENTO, COLOR_ERROR, COLOR_FONDO, COLOR_CABECERA,
    COLOR_SUPERFICIE, COLOR_SUPERFICIE_2, COLOR_TEXTO, COLOR_TEXTO_SUAVE,
    COLOR_SELECCION, RADIO, crear_tema, estilizar_campo, relleno,
)

PAGINA = 60                  # filas que se crean de golpe en la lista (el resto al hacer scroll)
LADO_PORTADA_LISTA = 44
ESPERA_ESCANEO_S = 30
ESPERA_INICIO_AUDIO_S = 15


class EstadoApp:
    """Estado compartido de la interfaz."""

    def __init__(self, carpeta: Path):
        self.carpeta: Path = carpeta
        self.biblioteca: list[Cancion] = []   # todo lo escaneado
        self.visibles: list[Cancion] = []     # lo que se ve (playlist + búsqueda)
        self.mostrando: int = 0               # cuántas de 'visibles' ya tienen fila
        self.cola = ColaReproduccion()        # lo que se reproduce (con modo aleatorio)
        self.playlist_actual: str | None = None
        self.reproduciendo: bool = False
        self.cargando_pista: bool = False     # evita eventos duplicados al cambiar de pista
        self.arrastrando: bool = False        # el usuario mueve la barra de progreso
        self.duracion_ms: int = 0
        self.vista: int = 0                   # móvil: 0 = biblioteca, 1 = descargar
        self.ruta_resaltada: str | None = None
        self.filas: dict[str, tuple] = {}     # ruta -> (icono, título, caja de portada)
        self.con_portada: set[str] = set()
        self.portadas = CachePortadas()
        self.indice_busqueda: dict[str, str] = {}
        self.generacion: int = 0              # invalida cargas de portadas de listas antiguas
        self.busqueda_pendiente: int = 0       # agrupa las pulsaciones de una misma búsqueda
        self.ancho_prev: float = 0.0          # para detectar giros de pantalla
        self.altura_max: float = 0.0          # mayor altura vista (referencia sin teclado)
        self.teclado: bool = False
        self.carga_visible: bool = False      # el indicador de carga está encendido en las vistas
        self.conectada = True
        self.escaneo = 0
        self.carpeta_escaneada = None


def main(page: ft.Page, plataforma: Plataforma):
    # ------------------------------------------------------------------ página
    page.title = "Mi Música"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = crear_tema()
    page.dark_theme = crear_tema()
    page.bgcolor = COLOR_FONDO
    page.padding = 0
    try:
        page.window.width = 1100
        page.window.height = 740
        page.window.min_width = 360
        page.window.min_height = 560
    except Exception:
        pass  # en móvil / web no existe la ventana

    est = EstadoApp(plataforma.carpeta_descargas())
    vistas: list = []   # barra de escritorio, mini y pantalla completa (se llenan más abajo)
    lector_portadas = ThreadPoolExecutor(max_workers=2, thread_name_prefix="portadas")
    lector_biblioteca = ThreadPoolExecutor(max_workers=2, thread_name_prefix="biblioteca")
    trabajos_portadas = []

    def al_desconectar(e):
        est.conectada = False
        est.generacion += 1
        est.escaneo += 1
        lector_portadas.shutdown(wait=False, cancel_futures=True)
        lector_biblioteca.shutdown(wait=False, cancel_futures=True)

    def al_conectar(e):
        nonlocal lector_portadas, lector_biblioteca
        if est.conectada:
            return
        est.conectada = True
        lector_portadas = ThreadPoolExecutor(max_workers=2, thread_name_prefix="portadas")
        lector_biblioteca = ThreadPoolExecutor(max_workers=2, thread_name_prefix="biblioteca")
        anillo_escaneo.visible = False
        refrescar_biblioteca()
        ajustar_diseno()

    page.on_disconnect = al_desconectar
    page.on_connect = al_conectar

    def en_todas(metodo: str, *args):
        """Aplica la misma actualización a todas las vistas del reproductor."""
        for v in list(vistas):
            try:
                getattr(v, metodo)(*args)
            except Exception as ex:
                diagnostico.registrar("vista", f"{type(v).__name__}.{metodo}: {ex}")

    # ----------------------------------------------- actualización entre hilos
    def seguro(funcion, *args):
        """
        Ejecuta 'funcion' en el bucle de eventos de Flet y luego refresca la página.
        Es la ÚNICA vía por la que los hilos de fondo tocan la interfaz.
        """
        async def _ejecutar():
            if not est.conectada:
                return
            try:
                funcion(*args)
                page.update()
            except Exception as ex:
                diagnostico.registrar("interfaz", f"{funcion.__name__}: {ex}")
        if not est.conectada:
            return
        try:
            page.run_task(_ejecutar)
        except Exception as ex:
            # Nunca modificar controles desde el hilo que descarga o escanea.
            diagnostico.registrar("interfaz", f"No se pudo programar actualización: {ex}")

    # ---------------------------------------------------------- avisos y diálogos
    def abrir_dialogo(dialogo):
        if isinstance(dialogo, ft.AlertDialog):
            dialogo.bgcolor = COLOR_SUPERFICIE
            dialogo.shape = ft.RoundedRectangleBorder(radius=20)
            dialogo.scrollable = True
        elif isinstance(dialogo, ft.SnackBar):
            dialogo.bgcolor = COLOR_SUPERFICIE_2
        try:
            page.show_dialog(dialogo)
        except AttributeError:
            page.overlay.append(dialogo)
            dialogo.open = True
            page.update()

    def cerrar_dialogo(dialogo):
        try:
            page.pop_dialog()
        except AttributeError:
            dialogo.open = False
            page.update()

    def alerta(titulo: str, mensaje: str):
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
            actions=[ft.TextButton("Aceptar", on_click=lambda e: cerrar_dialogo(dialogo))],
        )
        abrir_dialogo(dialogo)

    def aviso(mensaje: str):
        if repositorio.ultimo_error:
            mensaje += "\n" + repositorio.ultimo_error
        abrir_dialogo(ft.SnackBar(ft.Text(mensaje)))

    def protegido(funcion):
        """Un fallo de un control deja disponibles los demás y queda registrado."""
        def informar(ex):
            est.arrastrando = False
            diagnostico.registrar("acción", f"{funcion.__name__}: {type(ex).__name__}: {ex}")
            if est.conectada:
                alerta("No se pudo completar la acción", "Vuelve a intentarlo.\n\n" + str(ex)[:250])
        if inspect.iscoroutinefunction(funcion):
            @wraps(funcion)
            async def asincrona(*args, **kwargs):
                try:
                    return await funcion(*args, **kwargs)
                except Exception as ex:
                    informar(ex)
            return asincrona
        @wraps(funcion)
        def sincrona(*args, **kwargs):
            try:
                return funcion(*args, **kwargs)
            except Exception as ex:
                informar(ex)
        return sincrona

    # ======================================================================
    # PANEL DE DESCARGAS
    # ======================================================================
    portapapeles = ft.Clipboard()
    selector_carpeta = ft.FilePicker()
    page.services.append(portapapeles)
    page.services.append(selector_carpeta)

    async def pegar(e):
        try:
            texto = await portapapeles.get()
        except Exception:
            texto = None
        if not texto:
            aviso("El portapapeles está vacío.")
            return
        campo_url.value = texto.strip()
        boton_limpiar_url.visible = True
        page.update()

    def limpiar(e):
        campo_url.value = ""
        boton_limpiar_url.visible = False
        if not gestor.ocupado:
            barra_progreso.value = 0
            poner_estado("Listo", "info")
        page.update()

    def al_cambiar_url(e):
        boton_limpiar_url.visible = bool(campo_url.value)
        page.update()

    boton_limpiar_url = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="Limpiar",
                                      visible=False, on_click=limpiar)
    campo_url = ft.TextField(
        label="Enlace de música",
        hint_text="YouTube, YouTube Music o Spotify",
        prefix_icon=ft.Icons.LINK,
        suffix=ft.Row([ft.IconButton(icon=ft.Icons.CONTENT_PASTE, icon_size=20, tooltip="Pegar enlace",
                                     on_click=pegar), boton_limpiar_url], tight=True, spacing=0),
        filled=True,
        border=ft.OutlineInputBorder(border_radius=14),
        on_submit=lambda e: iniciar_descarga(),
        on_change=al_cambiar_url,
    )
    estilizar_campo(campo_url)

    icono_estado = ft.Icon(ft.Icons.INFO_OUTLINE, color=COLOR_TEXTO_SUAVE)
    texto_estado = ft.Text("Listo", color=COLOR_TEXTO_SUAVE, size=14, expand=True)
    barra_progreso = ft.ProgressBar(value=0, color=COLOR_ACENTO, bgcolor=COLOR_SUPERFICIE, bar_height=6)
    texto_carpeta = ft.Text(str(est.carpeta), size=12, color=COLOR_TEXTO_SUAVE,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, selectable=True)
    boton_descargar = ft.FilledButton("Descargar audio", icon=ft.Icons.DOWNLOAD, expand=True, height=48,
                                      on_click=lambda e: iniciar_descarga())
    boton_cancelar = ft.OutlinedButton("Cancelar", icon=ft.Icons.CANCEL, visible=False, height=48,
                                       on_click=lambda e: gestor.cancelar())

    @protegido
    async def cambiar_carpeta(e):
        ruta = await selector_carpeta.get_directory_path(dialog_title="Elige la carpeta de destino")
        if ruta:
            est.carpeta = Path(ruta)
            texto_carpeta.value = str(est.carpeta)
            page.update()
            refrescar_biblioteca()

    # ---- callbacks que ejecuta la interfaz cuando el hilo de descarga avisa ----
    def poner_estado(texto: str, tipo: str | None = None):
        if tipo is None:
            tipo = "descarga" if texto.startswith(
                ("Descargando", "Convirtiendo", "Escribiendo", "Guardando")) else "info"
        icono, color = {
            "info": (ft.Icons.INFO_OUTLINE, COLOR_TEXTO_SUAVE),
            "descarga": (ft.Icons.DOWNLOADING, COLOR_ACENTO),
            "ok": (ft.Icons.CHECK_CIRCLE, COLOR_ACENTO),
            "error": (ft.Icons.ERROR_OUTLINE, COLOR_ERROR),
        }[tipo]
        texto_estado.value = texto
        texto_estado.color = COLOR_TEXTO if tipo != "info" else COLOR_TEXTO_SUAVE
        icono_estado.name, icono_estado.color = icono, color

    def poner_progreso(valor):
        barra_progreso.value = valor

    def restaurar_botones():
        boton_descargar.disabled = False
        boton_cancelar.visible = False

    def al_terminar(descargados: int, errores: list, cancelado: bool):
        restaurar_botones()
        if cancelado:
            barra_progreso.value = 0
            poner_estado("Descarga cancelada", "info")
        elif descargados == 0:
            barra_progreso.value = 0
            poner_estado("No había nada nuevo que descargar (los archivos ya existían).", "info")
        else:
            barra_progreso.value = 1
            poner_estado(f"¡Completado! {descargados} canción(es) guardada(s).", "ok")
            if errores:
                alerta(
                    "Completado con avisos",
                    f"Se descargaron {descargados} canción(es), pero {len(errores)} elemento(s) fallaron.\n\n"
                    f"Primer error: {mensaje_error_amigable(errores[0])}",
                )
        refrescar_biblioteca()

    def al_fallar(mensaje: str):
        restaurar_botones()
        barra_progreso.value = 0
        poner_estado("Error: " + mensaje, "error")
        alerta("No se pudo descargar", mensaje)

    gestor = plataforma.crear_descargador(
        on_estado=lambda t: seguro(poner_estado, t),
        on_progreso=lambda v: seguro(poner_progreso, v),
        on_fin=lambda n, errs, canc: seguro(al_terminar, n, errs, canc),
        on_error=lambda m: seguro(al_fallar, m),
    )

    @protegido
    def iniciar_descarga():
        if gestor.ocupado:
            return
        url = validar_url(campo_url.value)
        if not url:
            alerta("Enlace no válido",
                   "Pega un enlace de YouTube o YouTube Music, o una canción o playlist pública "
                   "de open.spotify.com. Para Spotify, usa el enlace completo de la barra del navegador.")
            return
        problema = gestor.problema_de_entorno()  # se re-comprueba por si copiaron FFmpeg después
        if problema:
            alerta("Falta una herramienta", problema)
            return
        try:
            est.carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            alerta("Carpeta no válida", f"No se puede usar la carpeta de destino:\n{ex}")
            return

        boton_descargar.disabled = True
        boton_cancelar.visible = True
        barra_progreso.value = None  # animación indeterminada
        poner_estado("Conectando...", "descarga")
        page.update()
        try:
            gestor.iniciar(url, est.carpeta)
        except Exception as ex:
            al_fallar(mensaje_error_amigable(ex))

    problema_entorno = gestor.problema_de_entorno()
    aviso_entorno = ft.Text("⚠ " + (problema_entorno or ""), size=12, color=COLOR_ERROR,
                            visible=problema_entorno is not None)

    tarjeta_estado = ft.Container(
        bgcolor=COLOR_SUPERFICIE_2, border_radius=14, padding=14,
        content=ft.Column(spacing=10, controls=[
            ft.Row([icono_estado, texto_estado], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            barra_progreso,
        ]),
    )

    panel_descargas = ft.Container(
        bgcolor=COLOR_SUPERFICIE,
        border_radius=RADIO,
        padding=16,
        content=ft.Column(
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Column([ft.Text("Descargar música", size=24, weight=ft.FontWeight.BOLD),
                           ft.Text("YouTube · YouTube Music · Spotify", size=13,
                                   color=COLOR_TEXTO_SUAVE)], spacing=2),
                campo_url,
                ft.Text("Spotify: buscamos versiones equivalentes en YouTube. "
                        "Usa canciones o playlists públicas de menos de 100 canciones.",
                        size=12, color=COLOR_TEXTO_SUAVE),
                ft.Row([boton_descargar, boton_cancelar], spacing=8),
                tarjeta_estado,
                aviso_entorno,
                ft.Divider(height=1, color=COLOR_SUPERFICIE_2),
                ft.Text("Carpeta de destino", size=13, weight=ft.FontWeight.W_500),
                ft.Row([
                    ft.Container(texto_carpeta, expand=True),
                    ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Cambiar carpeta",
                                  on_click=cambiar_carpeta, visible=plataforma.permite_elegir_carpeta),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
        ),
    )

    # ======================================================================
    # PLAYLISTS, BIBLIOTECA Y PORTADAS
    # ======================================================================
    repositorio = RepositorioPlaylists(plataforma.carpeta_datos() / "playlists.json")

    texto_contador = ft.Text("Escaneando...", size=12, color=COLOR_TEXTO_SUAVE)
    anillo_escaneo = ft.ProgressRing(width=16, height=16, stroke_width=2, color=COLOR_ACENTO, visible=False)

    def limpiar_busqueda(e):
        campo_buscar.value = ""
        boton_limpiar_busqueda.visible = False
        aplicar_filtro()

    async def al_buscar(e):
        boton_limpiar_busqueda.visible = bool(campo_buscar.value)
        est.busqueda_pendiente += 1
        solicitud = est.busqueda_pendiente
        boton_limpiar_busqueda.update()
        await asyncio.sleep(0.18)
        if solicitud == est.busqueda_pendiente:
            aplicar_filtro()

    boton_limpiar_busqueda = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, visible=False,
                                           tooltip="Borrar búsqueda", on_click=limpiar_busqueda)
    campo_buscar = ft.TextField(
        hint_text="Buscar en tu biblioteca",
        prefix_icon=ft.Icons.SEARCH,
        suffix=boton_limpiar_busqueda,
        filled=True,
        border=ft.OutlineInputBorder(border_radius=10),
        border_color="transparent",
        bgcolor=COLOR_SUPERFICIE_2,
        text_size=13,
        dense=True,
        on_change=al_buscar,
        on_submit=lambda e: aplicar_filtro(),
    )
    estilizar_campo(campo_buscar)

    def al_scroll(e):
        """Crea más filas cuando el usuario se acerca al final de la lista."""
        if est.mostrando < len(est.visibles) and e.pixels >= (e.max_scroll_extent or 0) - 700:
            nuevas = agregar_filas(PAGINA)
            cargar_portadas(nuevas, est.generacion)
            page.update()

    lista_canciones = ft.ListView(expand=True, spacing=0, on_scroll=al_scroll, scroll_interval=120)
    fila_chips = ft.Row(spacing=8, height=44, scroll=ft.ScrollMode.AUTO)
    titulo_vacio = ft.Text("", size=18, weight=ft.FontWeight.BOLD,
                           text_align=ft.TextAlign.CENTER)
    ayuda_vacio = ft.Text("", size=13, color=COLOR_TEXTO_SUAVE,
                          text_align=ft.TextAlign.CENTER)
    icono_vacio = ft.Icon(ft.Icons.LIBRARY_MUSIC_OUTLINED, size=40, color=COLOR_TEXTO_SUAVE)
    estado_vacio = ft.Container(
        visible=False, expand=True, alignment=ft.Alignment.CENTER, padding=24,
        content=ft.Column([icono_vacio, titulo_vacio, ayuda_vacio], spacing=12,
                          tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
    )
    texto_playlist = ft.Text("", size=13, weight=ft.FontWeight.W_500, expand=True,
                             max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    # ---- diálogo genérico para pedir un nombre -------------------------------
    def dialogo_nombre(titulo: str, inicial: str, al_aceptar):
        campo = ft.TextField(value=inicial, autofocus=True, hint_text="Nombre de la playlist",
                             border=ft.OutlineInputBorder(border_radius=12))
        estilizar_campo(campo)

        def aceptar(e=None):
            nombre = (campo.value or "").strip()
            if not nombre:
                campo.error_text = "Escribe un nombre"
                page.update()
                return
            cerrar_dialogo(dialogo)
            al_aceptar(nombre)

        campo.on_submit = aceptar
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=campo,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(dialogo)),
                ft.FilledButton("Aceptar", on_click=aceptar),
            ],
        )
        abrir_dialogo(dialogo)

    # ---- playlists: chips de selección y acciones ------------------------------
    def reconstruir_chips():
        def chip(texto: str, id_):
            activo = est.playlist_actual == id_
            return ft.Container(
                height=40, padding=relleno(14, 0),
                bgcolor=COLOR_ACENTO if activo else COLOR_SUPERFICIE_2,
                tooltip=texto,
                content=ft.Row(tight=True, spacing=6, controls=[
                    ft.Icon(ft.Icons.LIBRARY_MUSIC if id_ is None else ft.Icons.QUEUE_MUSIC,
                            size=17, color=COLOR_FONDO if activo else COLOR_TEXTO_SUAVE),
                    ft.Text(
                        texto if len(texto) <= 24 else texto[:23] + "…",
                        size=12, weight=ft.FontWeight.W_600, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        color=COLOR_FONDO if activo else COLOR_TEXTO),
                ]),
                border_radius=20,
                ink=True,
                on_click=lambda e, i=id_: seleccionar_playlist(i),
            )

        fila_chips.controls = (
            [chip("Todas", None)]
            + [chip(p.nombre, p.id) for p in repositorio.listar()]
        )

    def seleccionar_playlist(id_):
        est.playlist_actual = id_
        lista = repositorio.obtener(id_) if id_ else None
        barra_playlist.visible = lista is not None
        texto_playlist.value = "Editar playlist" if lista else ""
        titulo_biblioteca.value = lista.nombre if lista else "Tu biblioteca"
        reconstruir_chips()
        aplicar_filtro()

    def nueva_playlist(archivo: str | None = None):
        def crear(nombre: str):
            lista = repositorio.crear(nombre)
            if archivo:
                repositorio.agregar(lista.id, archivo)
            reconstruir_chips()
            aviso(f"Playlist «{lista.nombre}» creada" + (" con la canción" if archivo else ""))
            page.update()
        dialogo_nombre("Nueva playlist", "", crear)

    def renombrar_playlist(e):
        lista = repositorio.obtener(est.playlist_actual) if est.playlist_actual else None
        if lista is None:
            return

        def renombrar(nombre: str):
            repositorio.renombrar(lista.id, nombre)
            seleccionar_playlist(lista.id)
        dialogo_nombre("Renombrar playlist", lista.nombre, renombrar)

    def eliminar_playlist(e):
        lista = repositorio.obtener(est.playlist_actual) if est.playlist_actual else None
        if lista is None:
            return

        def confirmar(e2):
            cerrar_dialogo(dialogo)
            repositorio.eliminar(lista.id)
            seleccionar_playlist(None)
            aviso(f"Playlist «{lista.nombre}» eliminada")

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar playlist"),
            content=ft.Text(f"¿Eliminar «{lista.nombre}»? Las canciones no se borran de tu biblioteca."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e2: cerrar_dialogo(dialogo)),
                ft.FilledButton("Eliminar", style=ft.ButtonStyle(bgcolor=COLOR_ERROR, color=COLOR_FONDO),
                                on_click=confirmar),
            ],
        )
        abrir_dialogo(dialogo)

    barra_playlist = ft.Row(
        visible=False,
        spacing=0,
        controls=[
            texto_playlist,
            ft.IconButton(icon=ft.Icons.EDIT, tooltip="Renombrar playlist", on_click=renombrar_playlist),
            ft.IconButton(icon=ft.Icons.DELETE, tooltip="Eliminar playlist", on_click=eliminar_playlist),
        ],
    )

    # ---- eliminar una canción (borra el archivo) ----------------------------------
    def confirmar_eliminar(cancion: Cancion):
        def aceptar(e):
            cerrar_dialogo(dialogo)
            page.run_task(borrar_cancion, cancion)

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar canción"),
            content=ft.Text(f"«{cancion.titulo}» se borrará de este dispositivo de forma permanente. "
                            "Esta acción no se puede deshacer."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: cerrar_dialogo(dialogo)),
                ft.FilledButton("Eliminar", style=ft.ButtonStyle(bgcolor=COLOR_ERROR, color=COLOR_FONDO), on_click=aceptar),
            ],
        )
        abrir_dialogo(dialogo)

    # ---- menú de cada canción (⋮ o pulsación larga) -----------------------------
    def menu_cancion(cancion: Cancion):
        def manejador(e):
            archivo = Path(cancion.ruta).name
            opciones: list = []

            if est.playlist_actual:
                def quitar(e2):
                    cerrar_dialogo(dialogo)
                    repositorio.quitar(est.playlist_actual, archivo)
                    aplicar_filtro()
                    aviso("Quitada de la playlist")
                opciones.append(ft.TextButton("Quitar de esta playlist",
                                              icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, on_click=quitar))

            opciones.append(ft.Text("Añadir a una playlist", size=12, color=COLOR_TEXTO_SUAVE))
            for lista in repositorio.listar():
                ya_esta = archivo in lista.archivos

                def agregar(e2, id_=lista.id, nombre=lista.nombre, ya=ya_esta):
                    cerrar_dialogo(dialogo)
                    if ya:
                        aviso(f"Ya estaba en «{nombre}»")
                        return
                    repositorio.agregar(id_, archivo)
                    if est.playlist_actual == id_:
                        aplicar_filtro()
                    aviso(f"Añadida a «{nombre}»")

                opciones.append(ft.TextButton(("✓ " if ya_esta else "") + lista.nombre, on_click=agregar))

            def nueva(e2):
                cerrar_dialogo(dialogo)
                nueva_playlist(archivo)
            opciones.append(ft.TextButton("Nueva playlist...", icon=ft.Icons.PLAYLIST_ADD, on_click=nueva))

            def eliminar(e2):
                cerrar_dialogo(dialogo)
                confirmar_eliminar(cancion)
            opciones.append(ft.Divider(height=1, color=COLOR_SUPERFICIE_2))
            opciones.append(ft.TextButton("Eliminar canción", icon=ft.Icons.DELETE_OUTLINE,
                                          style=ft.ButtonStyle(color=COLOR_ERROR), on_click=eliminar))

            dialogo = ft.AlertDialog(
                title=ft.Text(cancion.titulo, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                content=ft.Column(opciones, tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[ft.TextButton("Cerrar", on_click=lambda e2: cerrar_dialogo(dialogo))],
            )
            abrir_dialogo(dialogo)
        return manejador

    # ---- lista de canciones ---------------------------------------------------
    def pulsar_cancion(posicion: int):
        def manejador(e):
            est.cola.cargar(est.visibles, posicion)  # la cola es lo que se ve en pantalla
            page.run_task(reproducir_actual)
        return manejador

    def reproducir_lista(aleatorio: bool):
        """Botones 'Reproducir' / 'Aleatorio' de la lista que se está viendo."""
        def manejador(e):
            if not est.visibles:
                aviso("No hay canciones para reproducir.")
                return
            est.cola.aleatorio = aleatorio
            en_todas("aleatorio", est.cola.aleatorio)
            inicio = random.randrange(len(est.visibles)) if aleatorio else 0
            est.cola.cargar(est.visibles, inicio)
            page.run_task(reproducir_actual)
        return manejador

    def construir_fila(cancion: Cancion, posicion: int) -> ft.Control:
        activa = cancion.ruta == est.ruta_resaltada
        icono = ft.Icon(ft.Icons.GRAPHIC_EQ if activa else ft.Icons.MUSIC_NOTE,
                        color=COLOR_ACENTO if activa else COLOR_TEXTO_SUAVE, size=22)
        titulo = ft.Text(cancion.titulo, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                         color=COLOR_ACENTO if activa else COLOR_TEXTO,
                         weight=ft.FontWeight.BOLD if activa else ft.FontWeight.NORMAL)
        caja = ft.Container(
            width=LADO_PORTADA_LISTA, height=LADO_PORTADA_LISTA, border_radius=5,
            bgcolor=COLOR_SUPERFICIE_2, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            alignment=ft.Alignment.CENTER if hasattr(ft, "Alignment") else None,
            content=icono,
        )
        portada = est.portadas.get(cancion.ruta)
        if portada:
            caja.content = ft.Image(src=portada, width=LADO_PORTADA_LISTA,
                                    height=LADO_PORTADA_LISTA, cache_width=132, cache_height=132,
                                    fit=ft.BoxFit.COVER)
            est.con_portada.add(cancion.ruta)
        fila_visual = ft.Container(
            ink=True,
            border_radius=6,
            bgcolor=COLOR_SELECCION if activa else None,
            padding=relleno(0, 6),
            on_click=pulsar_cancion(posicion),
            on_long_press=menu_cancion(cancion),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    caja,
                    ft.Column(
                        expand=True, spacing=1,
                        controls=[
                            titulo,
                            ft.Text(cancion.artista, size=12, color=COLOR_TEXTO_SUAVE,
                                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                    ),
                    ft.Text(formato_tiempo(cancion.duracion), size=11, color=COLOR_TEXTO_SUAVE),
                    ft.IconButton(icon=ft.Icons.MORE_HORIZ, icon_size=20, icon_color=COLOR_TEXTO_SUAVE,
                                  tooltip=f"Opciones de {cancion.titulo}",
                                  on_click=menu_cancion(cancion)),
                ],
            ),
        )
        est.filas[cancion.ruta] = (icono, titulo, caja, fila_visual)
        return fila_visual

    def agregar_filas(cantidad: int) -> list[Cancion]:
        """Crea las siguientes 'cantidad' filas de la lista visible y devuelve esas canciones."""
        inicio = est.mostrando
        fin = min(len(est.visibles), inicio + cantidad)
        for i in range(inicio, fin):
            lista_canciones.controls.append(construir_fila(est.visibles[i], i))
        est.mostrando = fin
        return est.visibles[inicio:fin]

    def resaltar(ruta_nueva: str | None):
        """Marca la canción en reproducción y desmarca la anterior (sin reconstruir la lista)."""
        for ruta, activa in ((est.ruta_resaltada, False), (ruta_nueva, True)):
            fila = est.filas.get(ruta) if ruta else None
            if fila:
                icono, titulo, _caja, fondo = fila
                fondo.bgcolor = COLOR_SELECCION if activa else None
                titulo.color = COLOR_ACENTO if activa else COLOR_TEXTO
                titulo.weight = ft.FontWeight.BOLD if activa else ft.FontWeight.NORMAL
                if ruta not in est.con_portada:  # con portada no se muestra el icono
                    icono.name = ft.Icons.GRAPHIC_EQ if activa else ft.Icons.MUSIC_NOTE
                    icono.color = COLOR_ACENTO if activa else COLOR_TEXTO_SUAVE
        est.ruta_resaltada = ruta_nueva

    def poner_portadas_lista(generacion: int, lote: list):
        if generacion != est.generacion:
            return  # la lista cambió mientras se leían las portadas
        for ruta, datos in lote:
            fila = est.filas.get(ruta)
            if fila:
                fila[2].content = ft.Image(src=datos, width=LADO_PORTADA_LISTA,
                                           height=LADO_PORTADA_LISTA, cache_width=132, cache_height=132,
                                           fit=ft.BoxFit.COVER)
                est.con_portada.add(ruta)

    def cargar_portadas(canciones: list[Cancion], generacion: int):
        """Lee las portadas en segundo plano y las va mostrando por lotes."""
        rutas = [c.ruta for c in canciones if c.ruta not in est.portadas]
        if not rutas:
            return

        def tarea():
            lote: list = []
            for ruta in rutas:
                if est.generacion != generacion:
                    return
                try:
                    datos = est.portadas.leer(ruta, leer_portada)
                except Exception as ex:
                    diagnostico.registrar("portada", f"{ruta}: {ex}")
                    continue
                if datos:
                    lote.append((ruta, datos))
                if len(lote) >= 8:
                    seguro(poner_portadas_lista, generacion, list(lote))
                    lote.clear()
            if lote:
                seguro(poner_portadas_lista, generacion, lote)

        trabajos_portadas[:] = [trabajo for trabajo in trabajos_portadas if not trabajo.done()]
        if est.conectada:
            trabajos_portadas.append(lector_portadas.submit(tarea))

    def aplicar_filtro():
        est.busqueda_pendiente += 1
        lista_pl = repositorio.obtener(est.playlist_actual) if est.playlist_actual else None
        if est.playlist_actual and lista_pl is None:  # la playlist ya no existe
            est.playlist_actual = None
        base = repositorio.resolver(lista_pl, est.biblioteca) if lista_pl else est.biblioteca
        consulta = (campo_buscar.value or "").strip().lower()
        est.visibles = [
            c for c in base
            if not consulta or consulta in est.indice_busqueda.get(c.ruta, "")
        ]
        est.generacion += 1
        for trabajo in trabajos_portadas:
            trabajo.cancel()
        est.filas.clear()
        est.con_portada.clear()
        est.mostrando = 0
        lista_canciones.controls = []
        primeras = agregar_filas(PAGINA)
        cantidad = len(est.visibles)
        texto_contador.value = (f"{cantidad} resultado" + ("s" if cantidad != 1 else "") if consulta
                                else f"{cantidad} " + ("canción" if cantidad == 1 else "canciones"))
        estado_vacio.visible = not est.visibles
        lista_canciones.visible = bool(est.visibles)
        if consulta:
            icono_vacio.name = ft.Icons.SEARCH
            titulo_vacio.value = "No encontramos esa canción"
            ayuda_vacio.value = "Prueba con otro título, artista o álbum."
        elif lista_pl:
            icono_vacio.name = ft.Icons.QUEUE_MUSIC
            titulo_vacio.value = "Tu playlist empieza aquí"
            ayuda_vacio.value = "En Todas, abre las opciones de una canción y añádela a esta playlist."
        else:
            icono_vacio.name = ft.Icons.LIBRARY_MUSIC_OUTLINED
            titulo_vacio.value = "Tu música, en un solo lugar"
            ayuda_vacio.value = "Descarga tu primera canción desde Descargar o actualiza la biblioteca."
        botones_reproduccion.visible = bool(est.visibles)
        cargar_portadas(primeras, est.generacion)
        page.update()

    def aplicar_biblioteca(canciones: list, solicitud=None):
        if solicitud is not None and solicitud != est.escaneo:
            return
        anillo_escaneo.visible = False
        est.biblioteca = canciones
        est.indice_busqueda = {c.ruta: f"{c.titulo} {c.artista} {c.album}".lower() for c in canciones}
        est.portadas.invalidar()
        aplicar_filtro()

    def refrescar_biblioteca(e=None):
        """Escanea la carpeta en un hilo para no bloquear la interfaz."""
        if not est.conectada or (anillo_escaneo.visible and est.carpeta_escaneada == est.carpeta):
            return
        est.escaneo += 1
        solicitud = est.escaneo
        est.carpeta_escaneada = est.carpeta
        texto_contador.value = "Escaneando..."
        anillo_escaneo.visible = True
        page.update()
        carpeta = est.carpeta

        async def tarea():
            try:
                futuro = lector_biblioteca.submit(escanear_biblioteca, carpeta, plataforma.extensiones)
                canciones = await asyncio.wait_for(asyncio.wrap_future(futuro), ESPERA_ESCANEO_S)
                if est.conectada:
                    aplicar_biblioteca(canciones, solicitud)
            except Exception as ex:
                if est.conectada and solicitud == est.escaneo:
                    anillo_escaneo.visible = False
                    diagnostico.registrar("biblioteca", f"Error de escaneo: {type(ex).__name__}: {ex}")
                    texto_contador.value = "No se pudo actualizar. Vuelve a intentarlo."
                    aviso("Se conserva la biblioteca anterior. Pulsa Actualizar para reintentar.")
                    page.update()

        page.run_task(tarea)

    botones_reproduccion = ft.Row(
        visible=False,
        spacing=8,
        controls=[
            ft.IconButton(icon=ft.Icons.SHUFFLE, icon_size=23, icon_color=COLOR_TEXTO_SUAVE,
                          tooltip="Reproducir en aleatorio", on_click=reproducir_lista(True)),
            ft.IconButton(icon=ft.Icons.PLAY_ARROW, icon_size=34, width=54, height=54,
                          bgcolor=COLOR_ACENTO, icon_color="#111111",
                          tooltip="Reproducir", on_click=reproducir_lista(False)),
        ],
    )

    titulo_biblioteca = ft.Text("Tu biblioteca", size=24, weight=ft.FontWeight.BOLD,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    colecciones = ft.Row(spacing=4, controls=[
        ft.Container(fila_chips, expand=True),
        ft.IconButton(icon=ft.Icons.ADD, tooltip="Nueva playlist", on_click=lambda e: nueva_playlist()),
    ])
    panel_biblioteca = ft.Container(
        bgcolor=COLOR_SUPERFICIE,
        border_radius=RADIO,
        padding=ft.Padding(left=16, right=16, top=12, bottom=8),
        content=ft.Column(
            expand=True,
            spacing=10,
            controls=[
                ft.Row([
                    ft.Column([titulo_biblioteca, texto_contador],
                              spacing=0, expand=True),
                    anillo_escaneo,
                    botones_reproduccion,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([ft.Container(campo_buscar, expand=True),
                        ft.IconButton(icon=ft.Icons.REFRESH, icon_color=COLOR_TEXTO_SUAVE,
                                      tooltip="Actualizar biblioteca", on_click=refrescar_biblioteca)], spacing=4),
                colecciones,
                barra_playlist,
                lista_canciones,
                estado_vacio,
            ],
        ),
    )

    # ======================================================================
    # REPRODUCTOR (lógica; las tres vistas se construyen más abajo)
    # ======================================================================
    try:
        motor = plataforma.crear_reproductor(page)
        error_audio = None
    except Exception as ex:
        motor, error_audio = None, str(ex)

    def poner_carga(visible: bool):
        """Enciende o apaga el indicador de carga en todas las vistas (solo si cambia)."""
        if visible != est.carga_visible:
            est.carga_visible = visible
            en_todas("cargando", visible)

    def poner_reproduciendo(reproduciendo: bool):
        est.reproduciendo = reproduciendo
        en_todas("reproduciendo", reproduciendo)
        if not reproduciendo:
            poner_carga(False)  # en pausa o detenido no puede quedar nada "cargando"

    def alternar_aleatorio(e):
        est.cola.poner_aleatorio(not est.cola.aleatorio)
        en_todas("aleatorio", est.cola.aleatorio)
        aviso("Modo aleatorio activado" if est.cola.aleatorio else "Modo aleatorio desactivado")
        page.update()

    # --- barra de progreso: las tres vistas comparten estos manejadores ---
    def al_iniciar_arrastre():
        est.arrastrando = True

    def al_mover_barra(ms: float):
        en_todas("tiempo", int(ms))
        page.update()

    @protegido
    def al_soltar_barra(ms: float):
        if motor and not est.cola.vacia:
            try:
                motor.saltar(int(ms))
            except Exception as ex:
                alerta("No se pudo mover la reproducción", str(ex))
        est.arrastrando = False
        en_todas("progreso", int(ms), est.duracion_ms)
        page.update()

    @protegido
    def al_cambiar_volumen(v: float):
        if motor:
            motor.poner_volumen(v)
        barra_pc.volumen_icono(v)
        page.update()

    bloqueo_reproduccion = asyncio.Lock()
    solicitud_reproduccion = 0
    inicio_motor_pendiente = None

    async def reproducir_actual():
        nonlocal solicitud_reproduccion
        solicitud_reproduccion += 1
        solicitud = solicitud_reproduccion
        est.cargando_pista = True
        # Agrupa pulsaciones rápidas y ordena el acceso también al motor de escritorio.
        try:
            await asyncio.sleep(0.15)
            async with bloqueo_reproduccion:
                if solicitud != solicitud_reproduccion:
                    return
                await cargar_actual(solicitud)
        finally:
            if solicitud == solicitud_reproduccion:
                est.cargando_pista = False

    async def cargar_actual(solicitud):
        nonlocal inicio_motor_pendiente
        """Reproduce la canción que indica la cola. Primero el audio; la portada después."""
        cancion = est.cola.actual()
        if cancion is None:
            return
        if motor is None:
            alerta("Audio no disponible", error_audio or "No se pudo iniciar el motor de audio.")
            return
        if inicio_motor_pendiente is not None and not inicio_motor_pendiente.done():
            aviso("El motor aún está terminando la operación anterior. Puedes seguir usando la biblioteca y volver a intentarlo.")
            return
        if not Path(cancion.ruta).is_file():
            alerta("Archivo no encontrado", f"No existe:\n{cancion.ruta}\n\nActualiza la biblioteca.")
            return
        est.cargando_pista = True
        diagnostico.registrar("app", f"reproducir: {cancion.titulo}")
        cancelada = threading.Event()
        def iniciar_motor():
            try:
                motor.reproducir(cancion.ruta)
                if cancelada.is_set():
                    motor.detener()
            except Exception:
                if not cancelada.is_set():
                    raise

        def consumir_resultado(futuro):
            try:
                futuro.result()
            except Exception as ex:
                diagnostico.registrar("audio", f"Inicio fallido: {ex}")
        try:
            inicio_motor_pendiente = asyncio.get_running_loop().run_in_executor(None, iniciar_motor)
            inicio_motor_pendiente.add_done_callback(consumir_resultado)
            # Un hilo nativo no se puede cancelar: se mantiene aislado hasta que termine,
            # sin admitir otra carga simultánea y deteniendo cualquier inicio tardío.
            await asyncio.wait_for(asyncio.shield(inicio_motor_pendiente), ESPERA_INICIO_AUDIO_S)
            if solicitud != solicitud_reproduccion:
                motor.detener()
                return
            est.duracion_ms = int(cancion.duracion * 1000)
            en_todas("pista", cancion.titulo, cancion.artista, cancion.duracion)
            poner_reproduciendo(True)
            poner_carga(bool(getattr(motor, "cargando", lambda: False)()))
            resaltar(cancion.ruta)
            ajustar_diseno()  # muestra el mini-reproductor la primera vez
        except Exception as ex:
            cancelada.set()
            poner_reproduciendo(False)
            page.update()
            detalle = "El motor tardó demasiado en responder. Puedes volver a intentarlo cuando termine." if isinstance(ex, TimeoutError) else str(ex)
            alerta("No se pudo reproducir", f"{cancion.titulo}\n\n{detalle}")
            return
        # La portada se lee después de arrancar el audio para no retrasar el cambio de canción
        def mostrar_portada(datos):
            if solicitud == solicitud_reproduccion and est.cola.actual() is cancion:
                en_todas("portada", datos)

        def leer_portada_actual():
            try:
                datos = est.portadas.leer(cancion.ruta, leer_portada)
            except Exception as ex:
                diagnostico.registrar("portada", f"{cancion.ruta}: {ex}")
                datos = None
            seguro(mostrar_portada, datos)

        if est.conectada:
            trabajos_portadas.append(lector_portadas.submit(leer_portada_actual))

    async def pista_terminada():
        """Pasa sola a la siguiente (respeta el modo aleatorio); al final de la cola, se detiene."""
        if est.cola.siguiente() is not None:
            diagnostico.registrar("app", "fin de pista: pasa a la siguiente")
            await reproducir_actual()
        else:
            diagnostico.registrar("app", "fin de la cola")
            motor.detener()
            poner_reproduciendo(False)
            en_todas("progreso", 0, est.duracion_ms)
            if controles_multimedia is not None:
                controles_multimedia.cerrar()  # terminó la cola: se retira la notificación
            page.update()

    async def bucle_reproduccion():
        """Actualiza el progreso y detecta el fin de la pista (4 veces por segundo)."""
        ultimo_ms = -1
        fallos_seguidos = 0
        while True:
            await asyncio.sleep(0.25)
            if motor is None or est.cargando_pista:
                continue
            try:
                # Algo ajeno a la app (llamada, otra app con el foco de audio) pausó o reanudó el audio
                cambio = getattr(motor, "tomar_cambio_externo", lambda: None)()
                if cambio == "pausa":
                    diagnostico.registrar("app", "pausa externa: se refleja en la interfaz")
                    poner_reproduciendo(False)
                    page.update()
                elif cambio == "reanuda":
                    diagnostico.registrar("app", "reanudación externa: se refleja en la interfaz")
                    poner_reproduciendo(True)
                    page.update()
            except Exception:
                pass
            if not est.reproduciendo:
                continue
            try:
                if getattr(motor, "tomar_error", lambda: False)():
                    poner_reproduciendo(False)  # el motor ya mostró el aviso con el detalle
                    page.update()
                    continue
                if motor.terminado():
                    await pista_terminada()
                    continue
                cargando = bool(getattr(motor, "cargando", lambda: False)())
                if cargando != est.carga_visible:
                    poner_carga(cargando)
                    page.update()
                if not est.arrastrando and not cargando:
                    ms = min(motor.posicion_ms(), max(est.duracion_ms, 1000))
                    if ms != ultimo_ms:
                        ultimo_ms = ms
                        en_todas("progreso", ms, est.duracion_ms)
                        for vista in (barra_pc, mini, completo):
                            if vista.contenedor.visible:
                                vista.contenedor.update()
                fallos_seguidos = 0
            except Exception as ex:
                fallos_seguidos += 1
                if fallos_seguidos == 1:
                    diagnostico.registrar("reproducción", f"Error de actualización: {ex}")
                if fallos_seguidos >= 3:
                    poner_reproduciendo(False)
                    try:
                        motor.detener()
                    except Exception as error:
                        diagnostico.registrar("reproducción", f"No se pudo detener: {error}")
                    aviso("El reproductor dejó de responder. Pulsa Reproducir para volver a intentarlo.")
                    page.update()
                    fallos_seguidos = 0

    @protegido
    async def alternar_reproduccion(e):
        if motor is None:
            alerta("Audio no disponible", error_audio or "No se pudo iniciar el motor de audio.")
            return
        if est.cola.vacia:
            if not est.visibles:
                aviso("No hay canciones en la biblioteca.")
                return
            est.cola.cargar(est.visibles, 0)
            await reproducir_actual()
        elif not motor.activo:  # nunca se reprodujo, o se pulsó Stop
            await reproducir_actual()
        elif est.reproduciendo:
            motor.pausar()
            poner_reproduciendo(False)
            page.update()
        else:
            motor.reanudar()
            poner_reproduciendo(True)
            page.update()

    @protegido
    async def detener(e):
        nonlocal solicitud_reproduccion
        solicitud_reproduccion += 1
        est.cargando_pista = False
        if motor is None or est.cola.vacia:
            return
        motor.detener()
        poner_reproduciendo(False)
        en_todas("progreso", 0, est.duracion_ms)
        page.update()

    async def siguiente(e):
        if est.cola.siguiente() is not None:
            await reproducir_actual()

    @protegido
    async def anterior(e):
        """Si ya sonaron más de 3 s reinicia la canción; si no, vuelve a la anterior."""
        if est.cola.vacia:
            return
        if motor and motor.activo and motor.posicion_ms() > 3000:
            motor.saltar(0)
            en_todas("progreso", 0, est.duracion_ms)
            page.update()
            return
        est.cola.anterior()
        await reproducir_actual()

    def vaciar_reproductor():
        """Deja las vistas como al inicio: no hay canción actual."""
        est.ruta_resaltada = None
        est.duracion_ms = 0
        poner_reproduciendo(False)
        en_todas("pista", "Nada en reproducción", "", 0)
        en_todas("portada", None)
        en_todas("progreso", 0, 0)
        completo.cerrar()
        if controles_multimedia is not None:
            controles_multimedia.cerrar()

    async def borrar_cancion(cancion: Cancion):
        """Borra el archivo, la quita de playlists, biblioteca y cola, y ajusta la reproducción."""
        actual = est.cola.actual()
        era_actual = actual is not None and actual.ruta == cancion.ruta
        estaba_sonando = est.reproduciendo
        if era_actual and motor is not None:
            motor.detener()
            liberar = getattr(motor, "liberar", None)   # Windows no deja borrar un archivo abierto
            if liberar:
                await asyncio.to_thread(liberar)
            poner_reproduciendo(False)
        try:
            await asyncio.to_thread(eliminar_archivo, Path(cancion.ruta))
        except OSError as ex:
            alerta("No se pudo eliminar", f"{cancion.titulo}\n\n{ex}")
            page.update()
            return
        repositorio.quitar_de_todas(Path(cancion.ruta).name)
        est.portadas.pop(cancion.ruta, None)
        est.biblioteca = [c for c in est.biblioteca if c.ruta != cancion.ruta]
        era_actual_en_cola = est.cola.quitar(cancion.ruta)
        aplicar_filtro()
        aviso(f"«{cancion.titulo}» eliminada")
        if era_actual_en_cola:
            if estaba_sonando and est.cola.actual() is not None:
                await reproducir_actual()          # sigue con la siguiente
            else:
                est.cola.cargar([])                # no queda nada que reproducir
                vaciar_reproductor()
                ajustar_diseno()

    # ---- controles multimedia del sistema (panel de medios / teclas multimedia) ----
    @protegido
    async def desde_multimedia(accion: str, valor: int = 0):
        diagnostico.registrar("notificación", f"botón {accion}")
        if accion == "seek":
            if motor and not est.cola.vacia:
                motor.saltar(int(valor))
                est.arrastrando = False
                en_todas("progreso", int(valor), est.duracion_ms)
                page.update()
        elif accion == "play" and not est.reproduciendo:
            await alternar_reproduccion(None)
        elif accion == "pause" and est.reproduciendo:
            await alternar_reproduccion(None)
        elif accion == "siguiente":
            await siguiente(None)
        elif accion == "anterior":
            await anterior(None)
        elif accion == "stop":
            await detener(None)

    def pedir_multimedia(accion: str, valor: int = 0):
        """Lo llama el sistema (otro hilo o evento de la extensión); se reenvía al bucle de Flet."""
        page.run_task(desde_multimedia, accion, valor)

    def abrir_completo(e=None):
        if est.cola.actual() is None:
            return
        completo.abrir()
        page.update()

    def cerrar_completo(e=None):
        completo.cerrar()
        page.update()

    acciones = Acciones(
        alternar=alternar_reproduccion, anterior=anterior, siguiente=siguiente, detener=detener,
        aleatorio=alternar_aleatorio,
        arrastre_inicio=al_iniciar_arrastre, arrastre_mover=al_mover_barra, arrastre_fin=al_soltar_barra,
        volumen=al_cambiar_volumen, expandir=abrir_completo, colapsar=cerrar_completo,
    )
    barra_pc = BarraEscritorio(acciones)
    mini = MiniReproductor(acciones)
    completo = ReproductorCompleto(acciones)
    vistas.extend([barra_pc, mini, completo])
    controles_multimedia = None
    if plataforma.crear_controles_multimedia is not None:
        try:
            controles_multimedia = plataforma.crear_controles_multimedia(pedir_multimedia, page)
            vistas.append(controles_multimedia)
        except Exception:
            controles_multimedia = None  # sin controles del sistema la app funciona igual

    # ======================================================================
    # DISEÑO RESPONSIVO
    #   Escritorio (ancho >= 900): dos paneles + barra del reproductor abajo.
    #   Móvil: un panel a la vez + mini-reproductor + barra de navegación.
    #          Con el teclado abierto se ocultan encabezado, mini y navegación
    #          para que el campo de texto y la lista tengan todo el espacio.
    # ======================================================================
    def cambiar_vista(e):
        est.vista = int(e.control.selected_index)
        ajustar_diseno()

    barra_navegacion = ft.NavigationBar(
        bgcolor=COLOR_FONDO,
        indicator_color=COLOR_SELECCION,
        height=64,
        selected_index=0,
        on_change=cambiar_vista,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.LIBRARY_MUSIC_OUTLINED,
                                        selected_icon=ft.Icons.LIBRARY_MUSIC, label="Biblioteca"),
            ft.NavigationBarDestination(icon=ft.Icons.DOWNLOAD_OUTLINED,
                                        selected_icon=ft.Icons.DOWNLOAD, label="Descargar"),
        ],
    )

    cuerpo = ft.Row(
        [panel_descargas, panel_biblioteca],
        expand=True,
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    encabezado = ft.Container(
        bgcolor=COLOR_CABECERA,
        padding=relleno(12, 4),
        content=ft.Row([
            ft.Icon(ft.Icons.LIBRARY_MUSIC, color=COLOR_ACENTO, size=24),
            ft.Text("Mi Música", size=18, weight=ft.FontWeight.BOLD, expand=True),
            ft.IconButton(icon=ft.Icons.BUG_REPORT, icon_size=20, icon_color=COLOR_TEXTO_SUAVE,
                          tooltip="Diagnóstico", on_click=lambda e: abrir_diagnostico(e)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )

    def teclado_abierto(alto: float) -> bool:
        """Teclado en pantalla: por los 'insets' del sistema o, de respaldo, por la altura."""
        try:
            inset = float(page.media.view_insets.bottom or 0)
        except Exception:
            inset = 0.0
        return inset > 0 or (est.altura_max > 0 and alto < 0.72 * est.altura_max)

    def ajustar_diseno():
        ancho = float(page.width or 1100)
        alto = float(page.height or 740)
        if abs(ancho - est.ancho_prev) > 40:   # giro de pantalla o cambio grande de ventana
            est.altura_max = alto
        est.ancho_prev = ancho
        est.altura_max = max(est.altura_max, alto)

        escritorio = ancho >= ANCHO_MODO_ESCRITORIO
        est.teclado = (not escritorio) and teclado_abierto(alto)
        colecciones.visible = True
        hay_pista = est.cola.actual() is not None

        if escritorio:
            encabezado.visible = True
            barra_navegacion.visible = False
            barra_pc.contenedor.visible = True
            mini.contenedor.visible = False
            completo.contenedor.visible = False
            panel_descargas.visible = True
            panel_descargas.width = int(min(440, max(340, ancho * 0.34)))
            panel_descargas.expand = False
            panel_biblioteca.visible = True
        else:
            encabezado.visible = not est.teclado
            barra_navegacion.visible = not est.teclado
            barra_pc.contenedor.visible = False
            mini.contenedor.visible = hay_pista and not est.teclado
            completo.contenedor.visible = True
            completo.ajustar(ancho, alto)
            panel_descargas.visible = est.vista == 1
            panel_descargas.width = None
            panel_descargas.expand = True
            panel_biblioteca.visible = est.vista == 0
        panel_biblioteca.expand = True
        page.update()

    page.on_resize = lambda e: ajustar_diseno()
    page.on_media_change = lambda e: ajustar_diseno()

    def al_cambiar_ciclo_vida(e):
        """La app pasa a segundo plano / vuelve. Se registra y se avisa al reproductor."""
        estado = str(getattr(e.state, "value", e.state)).lower()
        diagnostico.registrar("ciclo de vida", estado)
        if motor is not None and hasattr(motor, "en_segundo_plano"):
            if estado in ("hide", "pause", "detach"):
                motor.en_segundo_plano(True)
            elif estado in ("show", "resume", "restart"):
                motor.en_segundo_plano(False)

    page.on_app_lifecycle_state_change = al_cambiar_ciclo_vida

    # ---- diálogo de diagnóstico (para investigar fallos que solo ocurren en el teléfono) ----
    async def copiar_diagnostico(e):
        resultado = portapapeles.set(diagnostico.texto(400))
        if asyncio.iscoroutine(resultado):
            await resultado
        aviso("Registro copiado al portapapeles")

    def abrir_diagnostico(e):
        texto_registro = ft.Text(diagnostico.texto(150), selectable=True, size=11, font_family="monospace")
        dialogo = ft.AlertDialog(
            title=ft.Text("Diagnóstico"),
            content=ft.Container(
                width=520, height=360,
                content=ft.Column([texto_registro], scroll=ft.ScrollMode.AUTO),
            ),
            actions=[
                ft.TextButton("Copiar todo", on_click=copiar_diagnostico),
                ft.TextButton("Cerrar", on_click=lambda e2: cerrar_dialogo(dialogo)),
            ],
        )
        abrir_dialogo(dialogo)

    # ---- atajos de teclado (escritorio): Ctrl+Espacio, Ctrl+←/→, Ctrl+F ----------
    async def al_teclado(e):
        if not e.ctrl:
            return
        tecla = (e.key or "").lower()
        if tecla in (" ", "space"):
            await alternar_reproduccion(None)
        elif tecla == "arrow right":
            await siguiente(None)
        elif tecla == "arrow left":
            await anterior(None)
        elif tecla == "f":
            resultado = campo_buscar.focus()
            if asyncio.iscoroutine(resultado):
                await resultado

    page.on_keyboard_event = al_teclado

    columna = ft.Column(
        expand=True,
        spacing=0,
        controls=[
            encabezado,
            ft.Container(cuerpo, expand=True),
            barra_pc.contenedor,
            mini.contenedor,
            barra_navegacion,
        ],
    )
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Stack(
                expand=True,
                controls=[
                    ft.Container(left=0, top=0, right=0, bottom=0, content=columna),
                    completo.contenedor,   # pantalla completa: se desliza desde abajo (móvil)
                ],
            ),
        )
    )

    # ----------------------------------------------------------- arranque
    reconstruir_chips()
    en_todas("aleatorio", est.cola.aleatorio)
    ajustar_diseno()
    refrescar_biblioteca()  # escaneo automático al iniciar
    page.run_task(bucle_reproduccion)
    if motor is None:
        alerta("Audio no disponible", f"No se pudo iniciar el reproductor: {error_audio}")
    if problema_entorno:
        alerta("Falta una herramienta",
               problema_entorno + "\n\nPodrás reproducir tu biblioteca, pero no descargar.")
    if repositorio.recuperado:
        aviso("Se recuperaron tus playlists desde el respaldo del último guardado.")
    elif repositorio.ultimo_error:
        aviso("Revisa tus playlists antes de guardar cambios.")
