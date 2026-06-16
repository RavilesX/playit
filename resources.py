# PlayIt - Reproductor de audio de escritorio con separación de pistas
# Copyright (C) 2025-2026  Ricardo Aviles Sanders
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
from pathlib import Path
from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QAbstractButton, QMessageBox
from typing import Union


def resource_path(relative_path: str) -> str:
    try:
        meipass = getattr(sys, '_MEIPASS', None)  # definido por PyInstaller
        base_path = Path(meipass) if meipass else Path.cwd()
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
    use_background: Union[bool, None] = None,
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

        meta = widget.metaObject()
        class_name = meta.className() if meta else type(widget).__name__
        widget.setStyleSheet(f"{class_name} {{ {' '.join(parts)} }}")

        if isinstance(widget, QLabel):
            widget.setScaledContents(True)

        return True
    except Exception as e:
        print(f"Error al asignar imagen a {widget}: {e}")
        return False
