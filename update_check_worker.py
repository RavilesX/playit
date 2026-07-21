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

import requests
from PyQt6.QtCore import QObject, pyqtSignal

GITHUB_API_LATEST_RELEASE = "https://api.github.com/repos/RavilesX/playit/releases/latest"


class UpdateCheckWorker(QObject):
    """Consulta el último release publicado en GitHub."""
    finished = pyqtSignal(str, str)  # (version, html_url)
    error = pyqtSignal(str)

    def run(self):
        try:
            response = requests.get(GITHUB_API_LATEST_RELEASE, timeout=10)
            response.raise_for_status()
            data = response.json()
            tag = data.get("tag_name", "")
            version = tag[1:] if tag.startswith("v") else tag
            self.finished.emit(version, data.get("html_url", ""))
        except requests.exceptions.RequestException:
            self.error.emit("No se pudo conectar con GitHub para buscar actualizaciones.\n"
                             "Revisa tu conexión a internet.")
        except Exception as e:
            self.error.emit(f"Error buscando actualizaciones: {e}")
