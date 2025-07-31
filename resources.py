import sys
import os
from pathlib import Path
from PyQt6.QtCore import QFile, QTextStream, QDir, QIODevice
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QAbstractButton
from typing import Union


def resource_path(relative_path):
    """Obtiene la ruta correcta para recursos"""
    try:
        base_path = Path(sys._MEIPASS if hasattr(sys, '_MEIPASS') else Path.cwd())
        path = base_path / relative_path
        return QDir.toNativeSeparators(str(path))
    except Exception as e:
        print(f"Resource path error: {e}")
        return QDir.toNativeSeparators(str(Path.cwd() / relative_path))

def bg_image(widget: Union[QWidget, QAbstractButton, QLabel],
                     image_path: str,
                     use_background: bool = None,
                     **css_properties) -> bool:
    """
    Asigna una imagen a cualquier widget Qt manejando automáticamente la propiedad correcta.

    Args:
        widget: Widget objetivo (QLabel, QPushButton, QFrame, etc.)
        image_path: Ruta relativa de la imagen
        use_background: Fuerza background-image (True) o image (False).
                       Si es None, decide automáticamente.
        **css_properties: Propiedades CSS adicionales (background-repeat, border, etc.)

    Returns:
        bool: True si se aplicó correctamente
    """
    try:
        # Obtener ruta formateada correctamente
        qt_path = style_url(image_path)  # Usando tu función style_url existente

        # Determinar la propiedad a usar
        if use_background is None:
            # Lógica automática basada en el tipo de widget
            if isinstance(widget, (QLabel, QAbstractButton)):
                prop = "image" if isinstance(widget, (QLabel,QPushButton)) else "background-image"
            else:
                prop = "background-image"
        else:
            prop = "background-image" if use_background else "image"

        # Construir el estilo CSS
        style_parts = [f"{prop}: url({qt_path});"]

        # Agregar propiedades adicionales
        for key, value in css_properties.items():
            style_parts.append(f"{key}: {value};")

        # Aplicar el estilo
        widget.setStyleSheet(f"""
            {widget.metaObject().className()} {{
                {' '.join(style_parts)}
            }}
        """)

        # Configuración adicional para algunos widgets
        if isinstance(widget, QLabel):
            widget.setScaledContents(True)

        return True

    except Exception as e:
        print(f"Error al asignar imagen a {widget}: {str(e)}")
        return False

def style_url(relative_path):
    """Para uso en stylesheets, convierte rutas a formato Qt válido"""
    path = resource_path(relative_path)
    return QDir.toNativeSeparators(path).replace('\\', '/')