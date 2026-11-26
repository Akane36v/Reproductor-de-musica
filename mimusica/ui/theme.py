"""Paleta y constantes visuales (tema oscuro estilo Spotify / YouTube Music)."""

COLOR_FONDO = "#0B0B0B"
COLOR_SUPERFICIE = "#151515"
COLOR_SUPERFICIE_2 = "#242424"
COLOR_ACENTO = "#1ED760"
COLOR_TEXTO = "#F5F5F5"
COLOR_TEXTO_SUAVE = "#ADADAD"
COLOR_CABECERA = "#151515"
COLOR_MINI = "#242424"
COLOR_ERROR = "#FF5252"
COLOR_BORDE = "#363636"
COLOR_SELECCION = "#173424"
RADIO = 12

# A partir de este ancho (px) se usa el diseño de escritorio de dos paneles;
# por debajo se usa el diseño vertical para móvil con barra de navegación.
ANCHO_MODO_ESCRITORIO = 900

COLOR_FONDO_SUAVE = "#173424"


def crear_tema():
    """Un mismo tema para pantallas, navegación, menús y diálogos."""
    import flet as ft
    forma = ft.RoundedRectangleBorder(radius=RADIO)
    return ft.Theme(
        color_scheme_seed=COLOR_ACENTO, scaffold_bgcolor=COLOR_FONDO,
        color_scheme=ft.ColorScheme(
            primary=COLOR_ACENTO, on_primary=COLOR_FONDO,
            primary_container=COLOR_SELECCION, on_primary_container=COLOR_TEXTO,
            secondary=COLOR_ACENTO, on_secondary=COLOR_FONDO,
            secondary_container=COLOR_SELECCION, on_secondary_container=COLOR_ACENTO,
            surface=COLOR_SUPERFICIE, on_surface=COLOR_TEXTO,
            on_surface_variant=COLOR_TEXTO_SUAVE, surface_tint="transparent",
            surface_container_lowest=COLOR_FONDO, surface_container_low=COLOR_SUPERFICIE,
            surface_container=COLOR_SUPERFICIE, surface_container_high=COLOR_SUPERFICIE_2,
            surface_container_highest=COLOR_BORDE, outline=COLOR_BORDE,
            outline_variant=COLOR_BORDE, error=COLOR_ERROR, on_error=COLOR_FONDO,
            inverse_surface=COLOR_SUPERFICIE_2, on_inverse_surface=COLOR_TEXTO),
        filled_button_theme=ft.FilledButtonTheme(style=ft.ButtonStyle(
            bgcolor={ft.ControlState.DEFAULT: COLOR_ACENTO, ft.ControlState.DISABLED: COLOR_SUPERFICIE_2},
            color={ft.ControlState.DEFAULT: COLOR_FONDO, ft.ControlState.DISABLED: COLOR_TEXTO_SUAVE},
            shape=ft.RoundedRectangleBorder(radius=24), padding=relleno(20, 12),
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_600))),
        outlined_button_theme=ft.OutlinedButtonTheme(style=ft.ButtonStyle(
            color=COLOR_TEXTO, side=ft.BorderSide(1, COLOR_BORDE), shape=forma)),
        text_button_theme=ft.TextButtonTheme(style=ft.ButtonStyle(
            color=COLOR_TEXTO, shape=forma, padding=relleno(16, 12))),
        icon_button_theme=ft.IconButtonTheme(style=ft.ButtonStyle(color=COLOR_TEXTO_SUAVE)),
        dialog_theme=ft.DialogTheme(
            bgcolor=COLOR_SUPERFICIE, shape=ft.RoundedRectangleBorder(radius=20),
            title_text_style=ft.TextStyle(size=20, weight=ft.FontWeight.BOLD, color=COLOR_TEXTO),
            content_text_style=ft.TextStyle(size=14, color=COLOR_TEXTO_SUAVE)),
        snackbar_theme=ft.SnackBarTheme(
            bgcolor=COLOR_SUPERFICIE_2, content_text_style=ft.TextStyle(color=COLOR_TEXTO),
            action_text_color=COLOR_ACENTO, shape=forma),
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor=COLOR_FONDO, indicator_color=COLOR_SELECCION,
            label_text_style=ft.TextStyle(size=12, color=COLOR_TEXTO)),
    )


def estilizar_campo(campo):
    """Aplica la misma superficie y foco al buscador, enlaces y nombres."""
    import flet as ft
    campo.filled = True
    campo.bgcolor = COLOR_SUPERFICIE_2
    campo.border = ft.OutlineInputBorder(border_radius=RADIO)
    campo.border_color = COLOR_BORDE
    campo.focused_border_color = COLOR_ACENTO
    campo.cursor_color = COLOR_ACENTO
    campo.color = COLOR_TEXTO
    campo.text_size = 14
    return campo


def relleno(horizontal: int, vertical: int):
    """Padding simétrico compatible con distintas versiones de Flet."""
    import flet as ft
    return ft.Padding.symmetric(horizontal=horizontal, vertical=vertical) if hasattr(ft, "Padding") else horizontal
