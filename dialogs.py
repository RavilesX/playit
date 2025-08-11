from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton, QLineEdit, QHBoxLayout
from resources import resource_path, bg_image


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sobre Playit")
        self.setFixedSize(450, 550)
        logo=resource_path('images/main_window/about.png')
        version=resource_path('images/main_window/version.png')
        about_text = f"""
        <style>
        li{{color:#b23c56;}}
        sub{{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}}
        </style>
        <center><img src="{version}"></center>
        <p>Reproductor de Audio que permite separación de pistas usando Demucs.</p>
        <b>CARACTERISTICAS:</b>
        <p>A) Separación en 4 pistas:</p>
        <li>:: Batería</li>
        <li>:: Voz</li>
        <li>:: Bajo</li>
        <li>:: Demas instrumentos</li>
        <li>:: - Función de separar pistas en queue -</li>
        <li>:: - Proceso No bloqueante de la interfaz -</li>
        <p>B) Control de volumen General</p>
        <p>C) Control de volumen Individual para cada track</p>
        <li>:: Clic sobre el instrumento para mutear</li>
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
        <li>* Desacoplable, (puede colocarse a la dercha o izquierda)</li>
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
                                background: transparent;
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

class SearchDialog(QDialog):
    search_requested = pyqtSignal(str)  # Señal para enviar el texto de búsqueda

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buscar en Playlist")
        self.setFixedSize(300, 150)

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