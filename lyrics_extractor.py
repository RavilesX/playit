import whisper_timestamped as whisper
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from lyrics_params import LyricsParams

class LyricsExtractorWorker(QObject):
    finished   = pyqtSignal(str)   # ruta .lrc generado
    error      = pyqtSignal(str)
    progress   = pyqtSignal(int)

    def __init__(self, params: LyricsParams):
        super().__init__()
        self.p = params
    # ----------  helpers  ----------
    def _format_time(self, seconds: float) -> str:
        mins  = int(seconds // 60)
        secs  = int(seconds % 60)
        cents = int((seconds % 1) * 100)
        return f"[{mins:02d}:{secs:02d}.{cents:02d}]"

    def _group_words(self, words):
        """Agrupa palabras cortando cuando haya > 0.6 seg de silencio."""
        lines, current, last_end = [], [], 0
        for w in words:
            gap = w["start"] - last_end
            if gap > 0.6 and current:          # corte por silencio
                lines.append(current)
                current = []
            current.append(w["text"].strip())
            last_end = w["end"]
        if current:
            lines.append(current)
        return lines

    def _insert_blanks(self, lines_data):
        """Inserta línea en blanco si hay > 5 s entre líneas."""
        out = []
        for i, (txt, start, end) in enumerate(lines_data):
            out.append((txt, start))
            if i < len(lines_data) - 1:
                nxt_start = lines_data[i+1][1]
                if nxt_start - end > 5 and out:
                    out.append(("", end + 0.01))
        return out

    def run(self):
        try:
            self.progress.emit(10)
            audio = whisper.load_audio(str(self.p.vocals_path))
            self.progress.emit(25)

            model = whisper.load_model(self.p.model_name)
            self.progress.emit(40)

            result = whisper.transcribe(model, audio, language="es")
            self.progress.emit(70)

            # --- construcción del contenido ---
            header = ''#(f'[00:00.00]<H1 style="color: #3AABEF;"><center>{self.p.artist}</center></H1>\n'
                      #f'<H2 style="color: #7E54AF;"><center>{self.p.song}</center></H2>\n')

            all_words = [w for seg in result["segments"] for w in seg["words"]]
            if not all_words:
                self.error.emit("No se detectaron palabras")
                return

            # agrupamos
            grouped = self._group_words(all_words)

            # lista de (texto, timestamp_inicio)
            lines_data = []
            idx = 0
            for g in grouped:
                txt   = " ".join(g)
                start = all_words[idx]["start"]
                end   = all_words[idx + len(g) - 1]["end"]
                lines_data.append((txt, start, end))
                idx += len(g)

            # insertamos líneas en blanco por >5 s de silencio
            final_lines = self._insert_blanks(lines_data)
            MIN_START = 0.5  # segundos
            final_lines = [(txt, t) for txt, t in final_lines if t >= MIN_START]

            # armamos el texto
            content = header
            for txt, t in final_lines:
                stamp = self._format_time(t)
                if txt == "":   # línea en blanco
                    content += f'{stamp}<center></center>\n'
                else:
                    content += f'{stamp}<center>{txt}</center>\n'

            with open(self.p.lrc_path, "w", encoding="utf-8") as f:
                f.write(content)

            self.progress.emit(100)
            self.finished.emit(str(self.p.lrc_path))

        except Exception as e:
            self.error.emit(str(e))