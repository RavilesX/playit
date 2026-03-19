import sys
from pathlib import Path
from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QAbstractButton, QMessageBox
from typing import Union


def resource_path(relative_path: str) -> str:
    try:
        base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path.cwd()
        path = base_path / relative_path

        if not path.exists():
            print(f"⚠️ Recurso no encontrado: {path}")

        return str(path)
    except Exception as e:
        print(f"Error en resource_path: {e}")
        return str(Path.cwd() / relative_path)


def style_url(relative_path: str) -> str:
    path = resource_path(relative_path)
    return QDir.toNativeSeparators(path).replace('\\', '/')


def styled_message_box(
    parent,
    title: str,
    text: str,
    icon=QMessageBox.Icon.Information,
    buttons=QMessageBox.StandardButton.Ok,
):
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStandardButtons(buttons)

    bg_path = style_url('images/main_window/bg_message_box.png')
    msg.setStyleSheet(f"""
        QMessageBox {{
            background-image: url({bg_path});
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


def bg_image(
    widget: Union[QWidget, QAbstractButton, QLabel],
    image_path: str,
    use_background: bool = None,
    **css_properties,
) -> bool:
    try:
        qt_path = style_url(image_path)

        if use_background is None:
            if isinstance(widget, (QLabel, QPushButton)):
                prop = "image"
            else:
                prop = "background-image"
        else:
            prop = "background-image" if use_background else "image"

        # Construir estilo
        parts = [f"{prop}: url({qt_path});"]
        parts.extend(f"{k}: {v};" for k, v in css_properties.items())

        class_name = widget.metaObject().className()
        widget.setStyleSheet(f"{class_name} {{ {' '.join(parts)} }}")

        if isinstance(widget, QLabel):
            widget.setScaledContents(True)

        return True
    except Exception as e:
        print(f"Error al asignar imagen a {widget}: {e}")
        return False
