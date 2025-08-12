from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPoint,QDir
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton, QLineEdit, QHBoxLayout, QFileDialog, QMessageBox
from resources import resource_path, bg_image,styled_message_box
from ui_components import DialogTitleBar
import os
import string
from PyQt6.QtGui import QPixmap
from pathlib import Path


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self._center()
        self.setWindowTitle("Sobre Playit")
        self.setFixedSize(450, 550)
        self._create_title_bar()

        version=resource_path('images/main_window/version.png')
        about_text = f"""
        <style>
        li{{color:#b23c56;}}
        sub{{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}}
        </style>
        <center><img src="{version}"></center>
        <p>Reproductor de Audio que permite separación de pistas usando Demucs.</p>
        <b>CARACTERÍSTICAS:</b>
        <p>A) Separación en 4 pistas:</p>
        <li>:: Batería</li>
        <li>:: Voz</li>
        <li>:: Bajo</li>
        <li>:: Otros instrumentos</li>
        <li>:: - Función de separar pistas en queue -</li>
        <li>:: - Proceso No bloqueante de la interfaz -</li>
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
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setHtml(about_text)
        self.text_edit.setStyleSheet("""
                            QTextEdit {
                                color: #fc5490;
                                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0
	                                                                rgba(0,0,0,0.7),stop:1 rgba(0,0,0,0.1));
                                border: 0px;
                                padding-top:2px;
                                font-size: 16px;                                
                            }
                        """)
        self.paypal_btn = QPushButton()
        self.paypal_btn.setFixedSize(70, 70)
        self.paypal_btn.setObjectName("aceptar_btn")
        bg_image(self.paypal_btn, "images/main_window/paypal.png")
        self.paypal_btn.clicked.connect(self.open_paypal_donation)

        layout = QVBoxLayout()
        layout.addWidget(self.title_bar)
        layout.addWidget(self.text_edit)
        layout.addWidget(QLabel("Se aceptan donaciones, por un mundo con software libre"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.paypal_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def open_paypal_donation(self):
        """Abre el enlace de PayPal en el navegador predeterminado"""
        paypal_url = QUrl("https://www.paypal.com/donate/?business=TULUZ868SK2BG&no_recurring=0&item_name=Desarrollo+apps+sin+fines+de+lucro%2C+no+necesitas+donar+para+usarlas%2C+pero+me+ayuda+y+me+inspira+a+seguir+creando+soluciones.&currency_code=USD")  # ¡REEMPLAZA CON TU ENLACE!

        if not paypal_url.isValid():
            print("¡Enlace de PayPal inválido!")
            return

        QDesktopServices.openUrl(paypal_url)

    def _create_title_bar(self):
        """Crea la barra de título personalizada."""
        self.title_bar = DialogTitleBar(self)
        self.title_bar.title.setText(self.windowTitle())

    def _center(self):
            parent_geo = self.parent.geometry()

            x = (parent_geo.width() // 2) - 225
            y = (parent_geo.height() // 2) - 275
            self.move(QPoint(x, y))

class SearchDialog(QDialog):
    search_requested = pyqtSignal(str)  # Señal para enviar el texto de búsqueda

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Buscar en Playlist")
        self.setFixedSize(300, 150)
        self.parent = parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self._center()

        # Crear la barra de título overradiada
        self._create_title_bar()

        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Introduce texto a buscar...")

        self.btn_accept = QPushButton()
        self.btn_accept.setObjectName("aceptar_btn")
        self.btn_accept.setFixedSize(70, 70)
        bg_image(self.btn_accept,"images/split_dialog/aceptar_btn.png")
        self.btn_accept.clicked.connect(self.accept_search)
        self.btn_accept.setDefault(True)
        self.btn_accept.setAutoDefault(True)

        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("cancelar_btn")
        self.btn_cancel.setFixedSize(70, 70)
        bg_image(self.btn_cancel, "images/split_dialog/cancelar_btn.png")
        self.btn_cancel.clicked.connect(self.reject)


        layout = QVBoxLayout()
        layout.addWidget(self.title_bar)
        layout.addWidget(self.search_text)
        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_accept)
        buttons.addWidget(self.btn_cancel)

        layout.addLayout(buttons)
        self.setLayout(layout)

    def accept_search(self):
        """Envía el texto y cierra el diálogo"""
        """Envía el texto sin limpiar el campo"""
        text = self.search_text.text().strip()
        if text:
            self.search_requested.emit(text)
        else:
            self.reject()

    def _create_title_bar(self):
        """Crea la barra de título personalizada."""
        self.title_bar = DialogTitleBar(self)
        self.title_bar.title.setText(self.windowTitle())

    def _center(self):
            parent_geo = self.parent.geometry()
            x = (parent_geo.width() // 2) - 150
            y = (parent_geo.height() // 2) - 75
            self.move(QPoint(x, y))


class QueueDialog(QDialog):
    queue_requested = pyqtSignal(str)

    def __init__(self, AudioPlayer, parent):
        super().__init__(parent)
        self.parent=parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self._center()
        self.setWindowTitle("Canciones en Cola")
        self.setFixedSize(400, 550)

        #Crear la barra de título overradiada
        self._create_title_bar()

        queue = f"<H1 style='color: #3AABEF;'><center>Artista - Canción</center></H1>" \
                f"<style>" \
                "li{color:#b23c56;}" \
                "sub{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}" \
                "</style><ul>\n"
        for element in AudioPlayer.demucs_queue:
            queue += f"<li><center>{element['artist']} - {element['song']}</center></li>\n"
        queue += "</ul>"
        self.queue_edit = QTextEdit()
        self.queue_edit.setReadOnly(True)
        self.queue_edit.setHtml(queue)
        self.queue_edit.setObjectName("queue_text")
        self.queue_edit.setStyleSheet("""
                                    #queue_text {
                                        color: #7E54AF;
                                        background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0
	                                                                rgba(0,0,0,0.5),stop:1 rgba(0,0,0,0.1));
                                        border: 0px;;
                                        padding-top:2px;
                                        font-size: 16px;                                
                                    }
                                """)

        layout = QVBoxLayout()
        layout.addWidget(self.title_bar)
        layout.addWidget(self.queue_edit)
        self.setLayout(layout)

    def _create_title_bar(self):
        """Crea la barra de título personalizada."""
        self.title_bar = DialogTitleBar(self)
        self.title_bar.title.setText(self.windowTitle())

    def _center(self):
            parent_geo = self.parent.geometry()

            x = (parent_geo.width() // 2) - 200
            y = (parent_geo.height() // 2) - 225
            self.move(QPoint(x, y))


class SplitDialog(QDialog):
    process_started = pyqtSignal(str, str, str)
    dialog_closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("splitDialog")
        # Cargar archivo de estilos css
        # with open('estilos.css', 'r') as file:
        #     style = file.read()
        # self.setStyleSheet(style)
        self.parent = parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self._center()
        self.setWindowTitle("Dividir Canción")
        self.setFixedSize(360, 440)
        self._create_title_bar()

        self.artist = QLineEdit()
        self.song = QLineEdit()
        self.song.setObjectName("SongText")

        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Presiona 'Enter'...")

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(self.title_bar)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Selección de archivo
        file_btn = QPushButton()
        file_btn.setObjectName("file_btn")
        file_btn.setFixedSize(200,100)
        bg_image(file_btn,"images/split_dialog/mp3.png")

        extract_name_btn = QPushButton()
        extract_name_btn.setFixedSize(120, 60)
        extract_name_btn.setObjectName("extract_name_btn")
        bg_image(extract_name_btn,"images/split_dialog/extract_name_btn.png")
        extract_name_btn.clicked.connect(self.extract_name)

        file_btn.clicked.connect(self._select_file)
        layout.addWidget(file_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.file_path)
        layout.addWidget(extract_name_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Campos obligatorios

        layout.addWidget(QLabel("Artista*"))
        layout.addWidget(self.artist)
        layout.addWidget(QLabel("Canción*"))
        layout.addWidget(self.song)

        # Botones
        btn_layout = QHBoxLayout()
        self.accept_btn = QPushButton()
        self.accept_btn.setObjectName("aceptar_btn")
        self.accept_btn.setFixedSize(70, 70)
        path_enable = QDir.toNativeSeparators(resource_path('images/split_dialog/aceptar_btn.png')).replace('\\', '/')
        path_disabled = QDir.toNativeSeparators(resource_path('images/split_dialog/aceptar_btn_disabled.png')).replace('\\', '/')
        style = f"""
                    QPushButton#aceptar_btn{{
                        image: url({path_enable});
                    }}
                    QPushButton#aceptar_btn:disabled{{
                        image: url({path_disabled});
                    }}
                    """
        self.accept_btn.setStyleSheet(style)

        self.accept_btn.clicked.connect(self._validate)
        cancel_btn = QPushButton()
        cancel_btn.setObjectName("cancelar_btn")
        cancel_btn.setFixedSize(70, 70)
        bg_image(cancel_btn,"images/split_dialog/cancelar_btn.png")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.accept_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Validación en tiempo real
        self.artist.textChanged.connect(self._enable_accept)
        self.song.textChanged.connect(self._enable_accept)
        self.file_path.textChanged.connect(self._enable_accept)
        self._enable_accept()

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar MP3", "", "MP3 Files (*.mp3)")
        if path:
            self.file_path.setText(path)

    def _enable_accept(self):
        required = [
            self.artist.text().strip(),
            self.song.text().strip(),
            self.file_path.text().strip()
        ]
        self.accept_btn.setEnabled(all(required))

    def _validate(self):
        if not Path(self.file_path.text()).exists():
            styled_message_box(self, "Error", "Archivo inválido", QMessageBox.Icon.Critical)
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
        self.hide()  # Oculta en lugar de cerrar
        self.dialog_closed.emit()  # Notificar que se ocultó

    def extract_name(self):
        teto=self.file_path.text()
        if not self.file_path.text():
            return

        # Obtener el nombre del archivo sin la ruta
        file = os.path.basename(self.file_path.text())

        # Separar nombre y extensión
        name, _ = os.path.splitext(file)

        # Verificar si hay guiones
        if '-' not in name:
            return

        # Dividir el nombre en partes usando guiones
        partes = name.split('-')

        # Construir resultados
        artist = partes[0]
        song = partes[-1]

        artist=artist.strip()
        song=song.strip()

        self.artist.setText(string.capwords(artist))
        self.song.setText(string.capwords(song))

    def _create_title_bar(self):
        """Crea la barra de título personalizada."""
        self.title_bar = DialogTitleBar(self)
        self.title_bar.title.setText(self.windowTitle())

    def _center(self):
            parent_geo = self.parent.geometry()

            x = (parent_geo.width() // 2) - 180
            y = (parent_geo.height() // 2) - 240
            self.move(QPoint(x, y))
