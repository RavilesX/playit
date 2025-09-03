from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPoint,QDir
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton, QLineEdit, QHBoxLayout, QFileDialog, QMessageBox
from resources import resource_path, bg_image,styled_message_box
from ui_components import DialogTitleBar
import os
import string
from pathlib import Path


class BaseDialog(QDialog):
    def __init__(self, parent=None, title: str = "", size: tuple[int, int] = (400, 300)):
        super().__init__(parent)
        self.parent = parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setFixedSize(*size)
        self._setup_ui()
        self._center()

    def _setup_ui(self):
        self._create_title_bar()
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.title_bar)
        self.setLayout(self.layout)

    def _create_title_bar(self):
        self.title_bar = DialogTitleBar(self)
        self.title_bar.title.setText(self.windowTitle())

    def _center(self):
        if not self.parent:
            return

        parent_geo = self.parent.geometry()
        x = (parent_geo.width() - self.width()) // 2
        y = (parent_geo.height() - self.height()) // 2
        self.move(QPoint(x, y))


class AboutDialog(BaseDialog):
    PAYPAL_URL = "https://www.paypal.com/donate/?business=TULUZ868SK2BG&no_recurring=0&item_name=Desarrollo+apps+sin+fines+de+lucro%2C+no+necesitas+donar+para+usarlas%2C+pero+me+ayuda+y+me+inspira+a+seguir+creando+soluciones.&currency_code=USD"

    def __init__(self, parent=None):
        super().__init__(parent, "Sobre Playit", (450, 550))
        self._setup_content()

    def _setup_content(self):
        text_edit = self._create_text_display()

        paypal_btn = self._create_paypal_button()

        # Layout
        self.layout.addWidget(text_edit)
        self.layout.addWidget(
            QLabel("Se aceptan donaciones, por un mundo con software libre"),
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.layout.addWidget(paypal_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _create_text_display(self) -> QTextEdit:
        version_path = resource_path('images/main_window/version.png')
        about_text = self._get_about_text(version_path)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(about_text)
        text_edit.setStyleSheet("""
            QTextEdit {
                color: #fc5490;
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:0, 
                    stop:0 rgba(0,0,0,0.7), stop:1 rgba(0,0,0,0.1)
                );
                border: 0px;
                padding-top: 2px;
                font-size: 16px;                                
            }
        """)
        return text_edit

    def _create_paypal_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(70, 70)
        btn.setObjectName("aceptar_btn")
        bg_image(btn, "images/main_window/paypal.png")
        btn.clicked.connect(self._open_paypal_donation)
        return btn

    def _open_paypal_donation(self):
        url = QUrl(self.PAYPAL_URL)
        if url.isValid():
            QDesktopServices.openUrl(url)
        else:
            print("Invalid PayPal URL!")

    def _get_about_text(self, version_path: str) -> str:
        return f"""
        <style>
        li{{color:#b23c56;}}
        sub{{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}}
        </style>
        <center><img src="{version_path}"></center>
        <p>Reproductor de Audio que permite separación de pistas usando Demucs.</p>
        <b>CARACTERÍSTICAS:</b>
        <p>A) Separación en 4 pistas:</p>
        <li>:: Batería</li>
        <li>:: Voz</li>
        <li>:: Bajo</li>
        <li>:: Otros instrumentos</li>
        <li> - Función de separar pistas en queue -</li>
        <li> - Proceso No bloqueante de la interfaz -</li>
        <p>B) Control de volumen General</p>
        <p>C) Control de volumen Individual para cada track</p>
        <li>:: Clic sobre el instrumento para silenciar</li>
        <li>:: Slider para bajar o subir el volumen</li>
        <p>D) Botones para control de reproducción</p>
        <li>:: Reproducir anterior</li>
        <li>:: Play/Pausa</li>
        <li>:: Reproducir Siguiente</li>
        <li>:: Detener reproducción</li>
        <p>E) Barra indicadora de progreso</p>
        <p>F) Mostrar Portada/Cover de Album</p>
        <p>G) Mostrar Letras/Lyrics</p>
        <p>H) Playlist</p>
        <li>* Puede mostrarse/ocultarse</li>
        <li>* Desmontable, (puede colocarse a la derecha o izquierda)</li>
        <p>I) Barra de Estado con información útil</p>
        <p>J) Selección de Carpeta para cargar la Playlist</p>
        <p>K) Dividir audio</p>
        <li>:: Selección de archivo Mp3</li>
        <li>:: Botón para extraer desde el nombre de archivo el nombre de artista/canción</li>
        <li>:: Opción para usar GPU en caso de tener instalado GPU Nvidia y el software CUDA</li>
        <li>:: Una vez completada la division, se agrega a la carpeta 'music_library' y no se tiene que dividir de nuevo</li>
        <p>L) Eliminar pistas de la playlist</p>
        <p>M) Buscar en playlist</p>
        <p>N) Modificar Lyrics</p>
        <li>:: Adelantar la visualización 0.5 segundos</li>
        <li>:: Retrasar la visualización 0.5 segundos</li>
        <li>:: Se Puede modificar el tamaño de la fuente</li>        
        <p>O) Limpiar la caché cargada</p>
        <sub>ESTE SOFTWARE SE PROPORCIONA 'TAL CUAL', SIN GARANTÍAS DE NINGÚN TIPO, YA SEAN EXPRESAS O IMPLÍCITAS, INCLUYENDO, PERO NO LIMITADO A, GARANTÍAS DE COMERCIABILIDAD, IDONEIDAD PARA UN PROPÓSITO PARTICULAR Y NO INFRACCIÓN. EN NINGÚN CASO, LOS AUTORES O COLABORADORES SERÁN RESPONSABLES DE DAÑOS DIRECTOS, INDIRECTOS, INCIDENTALES, ESPECIALES, EJEMPLARES O CONSECUENTES (INCLUYENDO, PERO NO LIMITADO A, LA ADQUISICIÓN DE BIENES O SERVICIOS SUSTITUTOS; LA PÉRDIDA DE USO, DATOS O BENEFICIOS; O LA INTERRUPCIÓN DEL NEGOCIO) DE CUALQUIER MANERA CAUSADOS Y BAJO CUALQUIER TEORÍA DE RESPONSABILIDAD, YA SEA POR CONTRATO, RESPONSABILIDAD ESTRICTA O AGRAVIO (INCLUYENDO NEGLIGENCIA O DE OTRA MANERA) QUE SURJA DE CUALQUIER FORMA DEL USO DE ESTE SOFTWARE, INCLUSO SI SE HA AVISADO DE LA POSIBILIDAD DE TALES DAÑOS.</sub>
        <p>Desarrollado por: RavilesX</p><p>Email: ravilesx@gmail.com</p>
        <p>Software Libre</p>        
        """


class SearchDialog(BaseDialog):
    search_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, "Buscar en Playlist", (300, 150))
        self._setup_search_ui()

    def _setup_search_ui(self):
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Introduce texto a buscar...")

        # Buttons
        btn_layout = self._create_button_layout()

        # Layout
        self.layout.addWidget(self.search_text)
        self.layout.addLayout(btn_layout)

    def _create_button_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        accept_btn = self._create_action_button(
            "aceptar_btn", "images/split_dialog/aceptar_btn.png",
            self._accept_search
        )
        accept_btn.setDefault(True)
        accept_btn.setAutoDefault(True)

        cancel_btn = self._create_action_button(
            "cancelar_btn", "images/split_dialog/cancelar_btn.png",
            self.reject
        )

        layout.addWidget(accept_btn)
        layout.addWidget(cancel_btn)
        return layout

    def _create_action_button(self, obj_name: str, image_path: str, callback) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName(obj_name)
        btn.setFixedSize(70, 70)
        bg_image(btn, image_path)
        btn.clicked.connect(callback)
        return btn

    def _accept_search(self):
        text = self.search_text.text().strip()
        if text:
            self.search_requested.emit(text)
            self.accept()
        else:
            self.reject()


class QueueDialog(BaseDialog):
    def __init__(self, audio_player, parent=None):
        super().__init__(parent, "Canciones en Cola", (400, 550))
        self._setup_queue_display(audio_player)

    def _setup_queue_display(self, audio_player):
        queue_html = self._generate_queue_html(audio_player.demucs_queue)

        queue_edit = QTextEdit()
        queue_edit.setReadOnly(True)
        queue_edit.setHtml(queue_html)
        queue_edit.setObjectName("queue_text")
        queue_edit.setStyleSheet("""
            #queue_text {
                color: #7E54AF;
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:0, 
                    stop:0 rgba(0,0,0,0.5), stop:1 rgba(0,0,0,0.1)
                );
                border: 0px;
                padding-top: 2px;
                font-size: 16px;                                
            }
        """)

        self.layout.addWidget(queue_edit)

    def _generate_queue_html(self, queue: list) -> str:
        html = """
        <H1 style='color: #3AABEF;'><center>Artista - Canción</center></H1>
        <style>
        li{color:#b23c56;}
        sub{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}
        </style><ul>
        """

        for item in queue:
            html += f"<li><center>{item['artist']} - {item['song']}</center></li>\n"

        html += "</ul>"
        return html


class SplitDialog(BaseDialog):
    process_started = pyqtSignal(str, str, str)
    dialog_closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, "Dividir Canción", (360, 440))
        self._setup_split_ui()

    def _setup_split_ui(self):
        self.artist = QLineEdit()
        self.song = QLineEdit()
        self.song.setObjectName("SongText")
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Presiona 'Enter'...")

        file_btn = self._create_file_button()

        extract_btn = self._create_extract_button()

        btn_layout = self._create_action_buttons()

        # Layout
        self.layout.addWidget(file_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.file_path)
        self.layout.addWidget(extract_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(QLabel("Artista*"))
        self.layout.addWidget(self.artist)
        self.layout.addWidget(QLabel("Canción*"))
        self.layout.addWidget(self.song)
        self.layout.addLayout(btn_layout)

        self._setup_validation()

    def _create_file_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("file_btn")
        btn.setFixedSize(200, 100)
        bg_image(btn, "images/split_dialog/mp3.png")
        btn.clicked.connect(self._select_file)
        return btn

    def _create_extract_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(120, 60)
        btn.setObjectName("extract_name_btn")
        bg_image(btn, "images/split_dialog/extract_name_btn.png")
        btn.clicked.connect(self._extract_name_from_file)
        return btn

    def _create_action_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.accept_btn = self._create_accept_button()
        cancel_btn = self._create_cancel_button()

        layout.addWidget(self.accept_btn)
        layout.addWidget(cancel_btn)
        return layout

    def _create_accept_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("aceptar_btn")
        btn.setFixedSize(70, 70)

        enabled_path = QDir.toNativeSeparators(
            resource_path('images/split_dialog/aceptar_btn.png')
        ).replace('\\', '/')
        disabled_path = QDir.toNativeSeparators(
            resource_path('images/split_dialog/aceptar_btn_disabled.png')
        ).replace('\\', '/')

        btn.setStyleSheet(f"""
            QPushButton#aceptar_btn{{
                image: url({enabled_path});
            }}
            QPushButton#aceptar_btn:disabled{{
                image: url({disabled_path});
            }}
        """)

        btn.clicked.connect(self._validate_and_start)
        return btn

    def _create_cancel_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("cancelar_btn")
        btn.setFixedSize(70, 70)
        bg_image(btn, "images/split_dialog/cancelar_btn.png")
        btn.clicked.connect(self.reject)
        return btn

    def _setup_validation(self):
        for field in [self.artist, self.song, self.file_path]:
            field.textChanged.connect(self._update_accept_button_state)
        self._update_accept_button_state()

    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar MP3", "", "MP3 Files (*.mp3)"
        )
        if file_path:
            self.file_path.setText(file_path)

    def _update_accept_button_state(self):
        required_fields = [
            self.artist.text().strip(),
            self.song.text().strip(),
            self.file_path.text().strip()
        ]
        self.accept_btn.setEnabled(all(required_fields))

    def _validate_and_start(self):
        if not Path(self.file_path.text()).exists():
            styled_message_box(
                self, "Error", "Archivo inválido",
                QMessageBox.Icon.Critical
            )
            return

        reply = styled_message_box(
            self,
            "Advertencia",
            "Dependiendo de su hardware, el proceso puede demorar varios minutos. ¿Continuar?",
            QMessageBox.Icon.Question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._start_process()

    def _start_process(self):
        self.process_started.emit(
            self.artist.text().strip(),
            self.song.text().strip(),
            self.file_path.text()
        )
        self.hide()
        self.dialog_closed.emit()

    def _extract_name_from_file(self):
        file_path = self.file_path.text()
        if not file_path:
            return

        filename = os.path.splitext(os.path.basename(file_path))[0]

        if '-' not in filename:
            return

        parts = filename.split('-')
        if len(parts) >= 2:
            artist = string.capwords(parts[0].strip())
            song = string.capwords(parts[-1].strip())

            self.artist.setText(artist)
            self.song.setText(song)