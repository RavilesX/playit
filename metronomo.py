import os
os.environ['SDL_AUDIODRIVER'] = 'directsound'
import pygame
from PyQt6.QtCore import Qt, QTimer, pyqtSignal,QRectF, QPointF
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
                             QDial, QLabel, QComboBox, QPushButton)
from PyQt6.QtGui import QColor, QPalette, QPainter, QPixmap
import math


class CustomDial(QDial):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.background = QPixmap("images/dial_bg.png")  # Imagen de fondo
        self.knob = QPixmap("images/knob.png")  # Imagen del knob

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dibujar fondo escalado proporcionalmente
        bg_scaled = self.background.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(self.rect(), bg_scaled)

        # Calcular posición del knob
        angle = self._calculate_angle()
        pos = self._knob_position(angle)

        # Dibujar knob rotado y centrado
        knob_scaled = self.knob.scaled(
            20, 20,  # Tamaño deseado del knob
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.translate(pos)
        painter.rotate(angle + 135)  # Ajustar ángulo inicial
        painter.drawPixmap(-knob_scaled.width() // 2, -knob_scaled.height() // 2, knob_scaled)
        painter.resetTransform()

    def _calculate_angle(self):
        """Convierte el valor del dial a ángulo (0-270 grados)"""
        return 270 * (self.value() - self.minimum()) / (self.maximum() - self.minimum())

    def _knob_position(self, angle):
        """Calcula posición (x,y) basada en ángulo y radio"""
        radius = min(self.width(), self.height()) // 2 - 25  # Radio ajustable
        center = self.rect().center()
        theta = math.radians(angle + 135)  # Ajuste de coordenadas Qt

        return QPointF(
            center.x() + radius * math.cos(theta),
            center.y() + radius * math.sin(theta))


class MetronomeDialog(QDialog):
    beat_signal = pyqtSignal(str,str)
    metronome_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        if not pygame.get_init():
            pygame.init()

        self.setWindowTitle("Metrónomo")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setFixedSize(250, 300)

        # Cargar archivo de estilos css
        with open('estilos.css', 'r') as file:
            style = file.read()
        self.setStyleSheet(style)

        # Valores por defecto
        self.default_bpm = 120
        self.default_measure = "4/4"

        self.timer = QTimer()
        self.timer.timeout.connect(self._play_beat)
        self.beat_count = 0
        self.current_measure = "4/4"
        self.bpm = 120
        self.is_playing = False

        self.init_ui()
        self._load_sounds()


        self.enable_check.stateChanged.connect(self._toggle_metronome)
        self.led_off_timer = QTimer()
        self.led_off_timer.setSingleShot(True)
        self.led_off_timer.timeout.connect(self._turn_off_leds)

    # def _emit_toggle_signal(self, state):
    #     """Envía el estado al AudioPlayer principal"""
    #     is_active = state == Qt.CheckState.Checked.value
    #     self.metronome_toggled.emit(is_active)  # Emitir señal

    def set_metronome_state(self, active):
        """Actualiza el checkbox desde el exterior"""
        self.enable_check.setChecked(active)


    def start_default(self):
        """Inicia el metrónomo con valores predeterminados"""
        if not self.is_playing:
            self.tempo_dial.setValue(self.default_bpm)
            self.time_signature.setCurrentText(self.default_measure)
            self.enable_check.setChecked(True)
            self.timer.start(500)  # Intervalo inicial (500ms = 120 BPM)

    def _start_metronome(self):
        """Inicia/reinicia el metrónomo"""
        self._stop_metronome()
        self.timer = QTimer()
        interval = int(60000 / self.bpm)
        self.timer.timeout.connect(self._play_beat)
        self.timer.start(interval)


    def _stop_metronome(self):
        """Detiene el metrónomo"""
        if hasattr(self, 'timer'):
            self.timer.stop()
            self.beat_signal.emit("black", "black")


    def init_ui(self):
        layout = QVBoxLayout()

        # Fila superior con checkbox y LEDs
        top_layout = QHBoxLayout()
        self.enable_check = QCheckBox("Activar")
        # self.enable_check.stateChanged.connect(self.toggle_metronome)

        # LEDs del diálogo
        # self.dialog_red_led = QLabel()
        # self.dialog_white_led = QLabel()
        # for led in [self.dialog_red_led, self.dialog_white_led]:
        #     led.setFixedSize(20, 20)
        #     led.setStyleSheet("background-color: black; border-radius: 10px;")

        top_layout.addWidget(self.enable_check)
        # top_layout.addWidget(self.dialog_red_led)
        # top_layout.addWidget(self.dialog_white_led)
        top_layout.addStretch()

        self.tempo_dial = CustomDial()
        self.tempo_dial.setRange(30, 240)
        self.tempo_dial.setValue(120)
        self.tempo_dial.setFixedSize(120,120)
        self.tempo_dial.setNotchesVisible(True)
        self.tempo_dial.valueChanged.connect(self._update_bpm)

        self.bpm_label = QLabel("120")
        self.tempo_dial.valueChanged.connect(lambda v: self.bpm_label.setText(f"{v}"))

        self.time_signature = QComboBox()
        self.time_signature.addItems(["1/4", "2/4", "3/4", "4/4", "5/4",
                                      "7/4", "5/8", "6/8", "7/8", "9/8", "12/8"])
        self.time_signature.setCurrentText("4/4")
        self.time_signature.currentTextChanged.connect(self._update_measure)


        BPM_layout = QHBoxLayout()
        knob_layout = QHBoxLayout()
        layout.addLayout(top_layout)
        BPM_layout.addWidget(QLabel("Beats por Minuto:"))
        BPM_layout.addWidget(self.bpm_label)
        knob_layout.addWidget(self.tempo_dial)
        layout.addLayout(BPM_layout)
        layout.addLayout(knob_layout)
        layout.addWidget(QLabel("Compás:"))
        layout.addWidget(self.time_signature)


        self.setLayout(layout)

    def _turn_off_leds(self):
        self.beat_signal.emit("black", "black")

    def update_leds(self, beat_type):
        colors = {
            "strong": ("red", "black"),
            "weak": ("black", "white"),
            "off": ("black", "black")
        }
        red, white = colors.get(beat_type, ("black", "black"))

        # Actualizar LEDs del diálogo
        self.dialog_red_led.setStyleSheet(f"background-color: {red}; border-radius: 10px;")
        self.dialog_white_led.setStyleSheet(f"background-color: {white}; border-radius: 10px;")

        # Actualizar LEDs principales
        parent = self.parentWidget()
        if parent:
            parent.update_main_leds.emit(red, white)  # Usar señal definida

    def showEvent(self, event):
        print("Ventana de metrónomo mostrada")  # Debug
        super().showEvent(event)

    def _load_sounds(self):
        try:
            # Inicializar mixer con suficientes canales
            pygame.mixer.init()#(frequency=44100, channels=4, buffer=1024)

            # Verificar disponibilidad de canales
            chan = pygame.mixer.get_num_channels()
            if pygame.mixer.get_num_channels() < 6:
                raise Exception("No hay suficientes canales de audio disponibles")

            # Usar canales dedicados
            self.metro_channel1 = pygame.mixer.Channel(4)  # Canal 2 para fuerte
            self.metro_channel2 = pygame.mixer.Channel(5)  # Canal 3 para débil

            self.strong_sound = pygame.mixer.Sound("sounds/fuerte.mp3")
            self.weak_sound = pygame.mixer.Sound("sounds/debil.mp3")

            print("Canales y sonidos cargados correctamente")  # Debug
        except Exception as e:
            print(f"Error cargando sonidos: {e}")
            self.metro_channel1 = None
            self.metro_channel2 = None

    def _toggle_metronome(self, state):
        """Maneja el checkbox de activación"""
        self.is_playing = state == Qt.CheckState.Checked.value
        self.enable_check.setText("Detener" if self.is_playing else "Activar")
        self.metronome_toggled.emit(self.is_playing)  # Emitir señal
        self._control_metronome()

    def _update_bpm(self, value):
        """Actualiza el BPM y reinicia el metrónomo si está activo"""
        self.bpm = value
        self.bpm_label.setText(f"{value} BPM")
        if self.is_playing:
            self._control_metronome()

    def _update_measure(self, measure):
        """Actualiza el compás"""
        self.current_measure = measure
        self.beat_count = 0

    # def _restart_metronome(self):
    #     was_playing = self.is_playing
    #     if self.is_playing:
    #         self.timer.stop()
    #         self.timer.timeout.disconnect()  # Desconectar todas las conexiones
    #
    #     self.beat_count = 0  # Resetear siempre el contador
    #
    #     if was_playing:
    #         self.update_interval()
    #         self.timer.start()

    def _control_metronome(self):
        """Control centralizado del metrónomo"""
        if self.is_playing:
            self._start_metronome()
        else:
            self._stop_metronome()

    def update_interval(self):
        if self.timer.isActive():
            self.timer.stop()

        if self.is_playing:
            try:
                self.timer.timeout.disconnect()  # Limpiar conexiones anteriores
            except TypeError:
                pass

            interval = int(60000 / self.bpm)
            self.timer.setInterval(interval)
            self.timer.timeout.connect(self._play_beat)
            self.timer.start()

    def _play_beat(self):
        # Detener todos los canales antes de reproducir
        # self.led_off_timer.stop()
        # if self.metro_channel2.get_busy():
        #     self.metro_channel2.stop()
        #
        # if self.metro_channel1.get_busy():
        #     self.metro_channel1.stop()

        beats = int(self.current_measure.split("/")[0])
        self.beat_count = (self.beat_count % beats) + 1

        # Reproducir sonido y encender LED
        if self.beat_count == 1:
            self.strong_sound.play()
            # Emitir colores para strong beat (rojo activo, blanco apagado)
            self.beat_signal.emit("red", "black")  # <--- Dos parámetros
        else:
            self.weak_sound.play()
            # Emitir colores para weak beat (blanco activo, rojo apagado)
            self.beat_signal.emit("black", "white")

        # Calcular tiempo de parpadeo (25% del intervalo total)
        flash_duration = int((60000 / self.bpm) * 0.25)
        self.led_off_timer.start(flash_duration)

        if self.beat_count >= beats:
            self.beat_count = 0


    def closeEvent(self, event):
        self.metronome_toggled.emit(self.enable_check.isChecked())
        self.hide()
        event.accept()