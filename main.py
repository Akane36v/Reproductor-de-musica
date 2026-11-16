"""Punto de entrada. Ejecutar con:  python main.py   (o:  flet run main.py)"""

import flet as ft

from mimusica.bootstrap import crear_plataforma
from mimusica.ui.app import main as main_ui


def main(page: ft.Page):
    main_ui(page, crear_plataforma())


if __name__ == "__main__":
    ft.run(main)
