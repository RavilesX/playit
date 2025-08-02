import sys
from pathlib import Path
from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QAbstractButton,QMessageBox
from typing import Union


def styled_message_box(parent, title, text, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
    """Crea un QMessageBox con estilo personalizado"""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStandardButtons(buttons)
    path = QDir.toNativeSeparators(resource_path('images/main_window/bg_message_box.png')).replace('\\', '/')
    msg.setStyleSheet(f"""
    QMessageBox {{
        background-image: url({path});
        background-repeat: no-repeat; 
        background-position: center;
    }}
    QLabel#qt_msgbox_label {{ 
        color: white;
        font-weight: bold;
    }}
    QPushButton {{
        min-width: 80px;
        color: white;
        background-color: #333;
    }}
    """)

    return msg.exec()

def resource_path(relative_path):
    """Obtiene la ruta correcta tanto para desarrollo como para el ejecutable"""
    try:
        # PyInstaller crea una carpeta temporal en _MEIPASS
        base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path.cwd()
        path = base_path / relative_path

        # Debug: Verificar existencia del archivo
        if not path.exists():
            print(f"⚠️ Recurso no encontrado: {path}")
            with open('missing_resources.log', 'a') as f:
                f.write(f"Missing: {path}\n")

        return str(path)
    except Exception as e:
        print(f"Error en resource_path: {e}")
        return str(Path.cwd() / relative_path)

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